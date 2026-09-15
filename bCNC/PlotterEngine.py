"""Application job service; its port supplies document and sender operations."""
from typing import Protocol, Sequence
from PlotterPlanning import JobParameters, prepare_job


class JobPort(Protocol):
    def blocks(self) -> Sequence: ...
    def parameters(self) -> JobParameters: ...
    def compensate(self, parameters: JobParameters) -> Sequence: ...
    def running(self) -> bool: ...
    def start(self): ...
    def pause(self): ...
    def stop(self): ...


class PlotterEngine:
    def __init__(self, jobs: JobPort):
        self.jobs = jobs

    def prepare(self, use_material=True):
        return prepare_job(self.jobs.blocks(), self.jobs.parameters(),
                           self.jobs.compensate, use_material=use_material)

    def sequence(self):
        from PlotterSequence import sequence_blocks, ToolStage
        from PlotterCompilation import compile_buffer
        return tuple(ToolStage(label, compile_buffer(blocks)) for label, blocks in
                     sequence_blocks(self.jobs.blocks(), self.jobs.parameters()))

    def preview(self):
        from PlotterSequence import sequence_blocks
        planned = sequence_blocks(self.jobs.blocks(), self.jobs.parameters())
        if planned:
            return [block for label, blocks in planned for block in blocks]
        return self.prepare()

    def start(self):
        return self.jobs.start()

    def pause(self):
        if self.jobs.running():
            return self.jobs.pause()

    def stop(self):
        return self.jobs.stop()
