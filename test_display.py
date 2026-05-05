"""Standalone test for set_leds and set_display tools — no Pi needed."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from robot.hardware.matrix import MockMatrix
from robot.tools.display import DisplayToolService, FACES, BUILTIN_ICONS
from robot.tools.leds import LedToolService


class PrintGpio:
    COLORS = {17: "\033[32m", 22: "\033[34m", 27: "\033[33m", 23: "\033[31m"}
    NAMES = {17: "GREEN", 22: "BLUE", 27: "YELLOW", 23: "RED"}
    RESET = "\033[0m"

    def set(self, pin: int, state: bool) -> None:
        color = self.COLORS.get(pin, "")
        name = self.NAMES.get(pin, f"PIN{pin}")
        symbol = f"{color}●{self.RESET}" if state else "○"
        print(f"  LED {name:6s} {symbol}")


class PrintMatrix(MockMatrix):
    def draw_grid(self, pixels: list[list[int]]) -> None:
        print("\033[2J\033[H")  # clear screen
        print("  ┌────────────────┐")
        for row in pixels[:8]:
            padded = (row + [0] * 8)[:8]
            line = "".join("██" if p else "  " for p in padded)
            print(f"  │{line}│")
        print("  └────────────────┘")

    def draw_text(self, text: str, scroll: bool = False) -> None:
        action = "SCROLL" if scroll else "SHOW"
        print(f"\n  [DISPLAY {action}]: {text}")

    def clear(self) -> None:
        print("\033[2J\033[H")
        print("  [DISPLAY CLEARED]")


async def demo_talking(display_svc: DisplayToolService) -> None:
    print("\n" + "=" * 50)
    print("  TALKING ANIMATION DEMO")
    print("=" * 50)

    for face_name in FACES:
        print(f"\n→ Setting face: {face_name}")
        await display_svc.handle({"face": face_name})
        await asyncio.sleep(1)

        print(f"→ Now talking with {face_name} face (2 seconds)...")
        display_svc.on_state_change("gemini_speaking")
        await asyncio.sleep(2)

        print(f"→ Stopped talking — back to static {face_name}")
        display_svc.on_state_change("listening")
        await asyncio.sleep(0.8)

    print("\n→ Icons (no talking animation):")
    for icon_name in BUILTIN_ICONS:
        await display_svc.handle({"icon": icon_name})
        await asyncio.sleep(0.8)


async def interactive(led_svc: LedToolService, display_svc: DisplayToolService) -> None:
    print("\n" + "=" * 50)
    print("  INTERACTIVE MODE")
    print("=" * 50)
    print("  Commands:")
    print("    face happy/sad/neutral/angry/surprised")
    print("    talk              — start talking animation")
    print("    stop              — stop talking")
    print("    icon heart/check/x/question/skull")
    print("    led green on      — turn on green LED")
    print("    text Hello        — show text")
    print("    scroll Hello      — scroll text")
    print("    clear             — clear display")
    print("    demo              — run talking demo")
    print("    quit              — exit")
    print()

    while True:
        try:
            cmd = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not cmd:
            continue
        parts = cmd.split()

        if parts[0] == "quit":
            break
        elif parts[0] == "demo":
            await demo_talking(display_svc)
        elif parts[0] == "face" and len(parts) >= 2:
            result = await display_svc.handle({"face": parts[1]})
            if "error" in result:
                print(f"  Error: {result['error']}")
        elif parts[0] == "talk":
            display_svc.on_state_change("gemini_speaking")
        elif parts[0] == "stop":
            display_svc.on_state_change("listening")
        elif parts[0] == "icon" and len(parts) >= 2:
            result = await display_svc.handle({"icon": parts[1]})
            if "error" in result:
                print(f"  Error: {result['error']}")
        elif parts[0] == "led" and len(parts) >= 3:
            name = parts[1]
            state = parts[2].lower() in ("on", "true", "1")
            result = await led_svc.handle({"leds": {name: state}})
            if "error" in result:
                print(f"  Error: {result['error']}")
        elif parts[0] == "text" and len(parts) >= 2:
            await display_svc.handle({"text": " ".join(parts[1:])})
        elif parts[0] == "scroll" and len(parts) >= 2:
            await display_svc.handle({"text": " ".join(parts[1:]), "scroll": True})
        elif parts[0] == "clear":
            await display_svc.handle({"clear": True})
        else:
            print("  Unknown command.")


async def main() -> None:
    gpio = PrintGpio()
    matrix = PrintMatrix()
    led_svc = LedToolService(gpio)
    display_svc = DisplayToolService(matrix)

    await demo_talking(display_svc)
    await interactive(led_svc, display_svc)

    led_svc.close()
    display_svc.close()
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
