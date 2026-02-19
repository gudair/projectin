"""
CLI Module

Terminal interface for the AI Trading Agent.
"""

# Lazy imports to avoid RuntimeWarning when running as __main__
def __getattr__(name):
    if name == 'run_cli':
        from cli.main import run_cli
        return run_cli
    elif name == 'Dashboard':
        from cli.dashboard import Dashboard
        return Dashboard
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ['run_cli', 'Dashboard']
