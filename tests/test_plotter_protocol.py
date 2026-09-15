"""Replay GRBL family reports and exercise a real sender against local TCP firmware."""
from pathlib import Path
import sys
import socket
import threading
import time
import unittest
from copy import deepcopy
from unittest.mock import Mock
from types import SimpleNamespace
from queue import Queue
ROOT = Path(__file__).resolve().parents[1]
for part in ('bCNC','bCNC/lib','bCNC/controllers'): sys.path.insert(0,str(ROOT/part))
import Helpers
import Utils
from CNC import CNC
from PlotterProtocol import Firmware, status_report


class ProtocolTest(unittest.TestCase):
    def test_version_capabilities_not_major_digit(self):
        for version, jog in [('0.8c',False),('0.9j',False),('1.0c',False),('1.1h',True)]:
            with self.subTest(version=version):
                f=Firmware(); f.observe(f"Grbl {version} ['$' for help]")
                self.assertTrue(f.identified); self.assertEqual(f.jog,jog)
                self.assertEqual(f.overrides,jog)
        f=Firmware(); f.observe('Grbl 1.9vendor [help]'); self.assertFalse(f.identified)
        f.observe('Grbl banana'); self.assertFalse(f.identified)

    def test_legacy_positions_and_modal_report(self):
        f=Firmware(); f.observe('Grbl 0.9j')
        values=status_report('<Idle,MPos:10,20,3,WPos:2,4,1>',f)
        self.assertEqual((values['wcox'],values['wcoy'],values['wcoz']),(8,16,2))
        self.assertFalse(f.jog)
        from GRBL0 import Controller
        master=self.master(); c=Controller(master)
        c.parseInformation('[G0 G54 G17 G21 G90 G94 M5 M9 T0 F300 S0]')
        self.assertEqual(CNC.vars['distance'],'G90')

    def test_position_order_wpos_and_two_axes(self):
        for report in ('<Idle|MPos:10,20,3|WCO:1,2,3>', '<Idle|WCO:1,2,3|MPos:10,20,3>'):
            f=Firmware(); values=status_report(report,f)
            self.assertEqual((values['wx'],values['wy'],values['wz']),(9,18,0))
        values=status_report('<Idle|WPos:4,5|WCO:1,2|Future:ignored>',Firmware())
        self.assertEqual((values['mx'],values['my'],values['mz']),(5,7,0))
        values=status_report('<Idle|MPos:1,2,3,4,5,6,7|WCO:0,0,0,0,0,0,0>',Firmware())
        self.assertEqual(values['mc'],6)

    def test_report_inches_invalidates_old_cache(self):
        f=Firmware(); status_report('<Idle|MPos:2,3,4|WCO:1,1,1>',f)
        f.observe('$13=1'); self.assertIsNone(f.last_wpos)
        values=status_report('<Idle|WPos:1,2,3|WCO:1,0,0|FS:10,500>',f)
        self.assertAlmostEqual(values['mx'],50.8); self.assertEqual(values['curfeed'],254)
        self.assertEqual(values['curspindle'],500)

    def test_bad_reports_are_atomic_and_do_not_invent_coordinates(self):
        f=Firmware(); self.assertNotIn('wx',status_report('<Idle|MPos:1,2,3>',f))
        before=deepcopy(f.__dict__)
        for report in ('<Idle|MPos:9,9,9|Ov:1>', '<Idle|MPos:nan,2,3>', '<Idle|MPos:1>', '<Idle'):
            with self.assertRaises(ValueError): status_report(report,f)
            self.assertEqual(f.__dict__,before)

    def test_grblhal_compatibility_identity_extensions_and_enumerations(self):
        f=Firmware()
        for line in ('Grbl 1.1f', '[VER:1.1f.20240506:]', '[NEWOPT:ENUMS,RT+,HOME]', '[FIRMWARE:grblHAL]'):
            f.observe(line)
        self.assertEqual(f.family,'grblHAL'); self.assertTrue(f.extended)
        self.assertIn('$I+',f.queries_due('Idle'))
        self.assertEqual(f.queries_due('Idle'),[])
        f.observe('[ALARMCODE:99||Driver needs attention]')
        f.observe('[ERRORCODE:88||Custom error]')
        f.observe('[SETTING:123|1|Travel|mm|6|0.0|0|300|0|0]')
        self.assertEqual(f.alarms[99],'Driver needs attention')
        self.assertEqual(f.errors[88],'Custom error')
        self.assertEqual(f.settings[123]['maximum'],'300')

    def test_discovery_in_alarm_hold_mpg_never_resets_or_unlocks(self):
        f=Firmware()
        for state in ('Alarm:10','Hold:0','Door:1','Run','Tool'):
            self.assertEqual(f.queries_due(state),[])
        status_report('<Idle|MPG:1>',f); self.assertEqual(f.queries_due('Idle'),[])
        status_report('<Idle>',f); self.assertTrue(f.mpg)
        status_report('<Idle|MPG:0>',f)
        self.assertEqual(f.queries_due('Idle'),['$I','$G','$$'])
        f.started-=6; self.assertTrue(f.timed_out)

    def test_manual_override_requires_observed_reports_and_units(self):
        f=Firmware('GRBL0'); self.assertFalse(f.identified)
        status_report('<Idle,MPos:1,2,0,WPos:1,2,0>',f)
        self.assertTrue(f.identified); self.assertFalse(f.ready); self.assertFalse(f.jog)
        f.observe('$13=0'); self.assertTrue(f.ready); self.assertTrue(f.manual)

    def test_partial_lines_and_crlf_are_preserved(self):
        from PlotterProtocol import LineFramer
        f = LineFramer()
        self.assertEqual(f.feed(b'GrblHAL 1.'), [])
        self.assertEqual(f.feed(b"1f\r\nok\n<Idle|MP"), ['GrblHAL 1.1f','ok'])
        self.assertEqual(f.feed(b'os:1,2,3>\n'), ['<Idle|MPos:1,2,3>'])
        with self.assertRaises(ValueError): f.feed(b'x'*65537)

    def test_08_setting_names_are_not_mislabeled_as_11(self):
        from GRBL0 import Controller
        master = self.master(); controller = Controller(master)
        controller.parseLine('Grbl 0.8c',[],[])
        controller.parseLine('$0=119.339 (x, step/mm)',[],[])
        self.assertEqual(CNC.vars['grbl_0'], '119.339')
        self.assertEqual(master.firmware.settings[0]['name'], 'x, step/mm')
        self.assertNotIn('$I', master.firmware.queries_due('Idle'))

    def master(self):
        return SimpleNamespace(log=Queue(), MSG_RECEIVE=2, MSG_ERROR=4, MSG_OK=3,
            firmware=None, running=False, _alarm=False,
            sio_status=False, sio_wait=False, _gcount=0, _msg=None,
            sendGCode=Mock(), runEnded=Mock(), emptyQueue=Mock())

    def test_restart_ends_job_without_unlock_and_clears_discovery(self):
        from GRBL1 import Controller
        master=self.master(); master.running=True; master.firmware=Firmware()
        master.firmware.observe('Grbl 1.1h'); master.firmware.queries_due('Idle')
        c=Controller(master); commands=['G1 X2']; lengths=[6]
        c.parseLine("GrblHAL 1.1f ['$' for help]",lengths,commands)
        master.runEnded.assert_called_once(); master.emptyQueue.assert_called_once()
        master.sendGCode.assert_not_called()
        self.assertFalse(master.firmware.ready); self.assertEqual(commands,[])
        self.assertEqual(master.firmware.queries,set())

    def test_unknown_square_fields_and_exact_acknowledgements(self):
        from GRBL1 import Controller
        master=self.master(); c=Controller(master); lengths=[4]; lines=['G0']
        c.parseLine('look here',lengths,lines); self.assertEqual(lengths,[4])
        c.parseLine('[GC:G0 G21 G90 G94 M5 F300 S0]',lengths,lines)
        c.parseLine('[G92:1,2]',lengths,lines); self.assertEqual(CNC.vars['G92Z'],0)
        c.parseLine('[G28:invalid]',lengths,lines)
        c.parseLine('ok',lengths,lines); self.assertEqual(lengths,[])

    def test_real_tcp_sender_discovers_grblhal_without_banner_or_motion(self):
        from Sender import Sender
        listener=socket.socket(); listener.bind(('127.0.0.1',0)); listener.listen(1); listener.settimeout(3)
        received=[]; failures=[]; stop=threading.Event()
        def firmware_server():
            try:
                client,_=listener.accept()
                with client:
                    client.settimeout(.2); pending=b''
                    while not stop.is_set():
                        try: data=client.recv(1024)
                        except socket.timeout: continue
                        if not data: break
                        for byte in data:
                            if byte in (ord('?'),0x80):
                                client.sendall(b'<Idle|WCO:0,0,0|MPos:10,20,0>\n'); continue
                            pending+=bytes([byte])
                            if byte==10:
                                command=pending.decode().strip(); pending=b''; received.append(command)
                                if command in ('$I','$I+'):
                                    client.sendall(b'[VER:1.1f.20240506:]\n[NEWOPT:ENUMS,RT+]\n[FIRMWARE:grblHAL]\n')
                                if command=='$$': client.sendall(b'$13=0\n')
                                if command=='$G': client.sendall(b'[GC:G0 G21 G90 G94 M5 F300 S0]\n')
                                client.sendall(b'ok\n')
            except Exception as error: failures.append(error)
        worker=threading.Thread(target=firmware_server,daemon=True); worker.start()
        Utils.loadConfiguration()
        sender=Sender(); sender.stopRun=lambda: None
        try:
            sender.open(f'socket://127.0.0.1:{listener.getsockname()[1]}',115200)
            deadline=time.monotonic()+4
            while time.monotonic()<deadline and not (sender.firmware.ready and '$ES' in received and sender.queue.empty() and sender._sumcline == 0): time.sleep(.02)
            self.assertTrue(sender.firmware.ready)
            self.assertEqual(sender.firmware.family,'grblHAL')
            self.assertIn('$I+',received)
            self.assertEqual(sender._sumcline, 0)
            self.assertTrue(sender.queue.empty())
            self.assertTrue(all(c in ('$I','$I+','$G','$$','$EA','$EE','$ES') for c in received),received)
        finally:
            reader=sender.thread
            Sender.close(sender); stop.set(); listener.close(); worker.join(3)
            if reader: reader.join(3)
        self.assertEqual(failures,[])


if __name__=='__main__': unittest.main()
