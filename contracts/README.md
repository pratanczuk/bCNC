# Shared compatibility contracts

Classic and Next use `foil-studio-project`, version 1, with millimetre coordinates.
The classic implementation in `bCNC/PlotterProject.py` is the current compatibility reference.
Fixtures here must be changed deliberately on both branches, with a compatibility test.
Unknown future format versions must be rejected; never overwrite a project whose version
cannot be read. Next initially opens projects for preview only. Writing, editing and
machine execution are separate acceptance gates, not implied by preview support.

`fixtures/projects/rectangle.foil` is a synthetic, redistributable reference project.
Next must preserve unknown fields before gaining save support. Planning parity requires
additional fixtures for arcs, transforms, text, layers, passes and pen/knife sequencing.
