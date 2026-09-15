"""Report full-app coverage and enforce >90% for the workflow and dialog UI layer.

Run after coverage run --source=bCNC -m unittest discover -s tests under Xvfb.
Nothing is omitted from data collection; the UI gate and total are separate.
"""
from pathlib import Path
import coverage


GUI_MODULES = (
    'PlotterAdaptive', 'PlotterUI', 'PlotterMachineUI', 'PlotterWorkflow',
    'PlotterAdvanced', 'PlotterConnection', 'PlotterDesign', 'PlotterLayersUI',
    'PlotterLibraryUI', 'PlotterProjectUI', 'PlotterSettings', 'PlotterStudio',
    'PlotterTrace', 'PlotterTheme', 'PlotterErrorDialog',
)


def main():
    cov = coverage.Coverage()
    cov.load()
    cov.report()
    print('\nWorkflow and dialog UI layer (new and reused modules):')
    includes = [f'*/{name}.py' for name in GUI_MODULES]
    percent = cov.report(include=includes, precision=2, show_missing=True)
    Path('artifacts/coverage').mkdir(parents=True, exist_ok=True)
    cov.json_report(outfile='artifacts/coverage/application.json')
    cov.json_report(include=includes, outfile='artifacts/coverage/gui.json')
    cov.html_report(directory='htmlcov')
    if percent <= 90:
        raise SystemExit(f'GUI coverage must be greater than 90%; got {percent:.2f}%')
    print(f'GUI coverage gate passed: {percent:.2f}% > 90%')


if __name__ == '__main__':
    main()
