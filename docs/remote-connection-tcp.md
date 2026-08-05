# Remote Connection to Plotter from bCNC (Socket / Network TCP)

You can run bCNC on your main PC and connect remotely over the network using a TCP socket connection.

The tablet acts as a network serial bridge to the plotter controller and listens on port `8888`.

## Step-by-Step PC Setup
1. Launch **bCNC** on your PC.
2. Go to the **File** tab.
3. In the **Connection** panel, change the connection type/port from a local serial port (for example, `COM3` or `/dev/ttyUSB0`) to:

```text
socket://plotter.local:8888
```

If `plotter.local` does not resolve on your network, use the tablet IP address instead, for example:

```text
socket://192.168.1.50:8888
```

4. Click **Open** to establish the network link.

## Notes & Troubleshooting
- **Firewall / Port Access**: Ensure port `8888` is not blocked by a firewall on either the PC or the tablet.
- **Network Latency**: For smooth real-time jogging and emergency stop response, ensure both PC and tablet have a stable Wi-Fi or Ethernet connection.
- **Host Resolution**: If mDNS is unavailable, use a static IP or DHCP reservation for reliable connectivity.
