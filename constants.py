class ColorPainter:
    def __init__(self):
        # Mapping of numerical ANSI string codes
        self.codes = {
            "red": "31", "green": "32", "yellow": "33",
            "blue": "34", "magenta": "35", "cyan": "36", "gray": "90"
        }

    def __getattr__(self, name):
        """Intercepts calls like .red(...) dynamically."""
        if name in self.codes:
            def painter(text, b=False, u=False):
                modifiers = [self.codes[name]]
                if b: modifiers.append("1")
                if u: modifiers.append("4")
                return f"\033[{';'.join(modifiers)}m{text}\033[0m"
            return painter
        raise AttributeError(f"ColorPainter has no attribute '{name}'")


c = ColorPainter()

### Global variables ###
SAVED = c.green("[Saved]")
ERROR = c.red("[Error]")
WARN = c.yellow("[Warn]")
SUCC = c.green("[Succ]")
WAIT = c.gray("[Wait]")
