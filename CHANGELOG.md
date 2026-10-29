# Changelog

## 0.4.0 - 2026-10-29

- **Fly.** Right-click > Fly: the bird takes off, hovers for a few seconds and lands. The bake's airborne part is
  looped seamlessly (it is exactly periodic), the bird rises about a third of its height, and the ground shadow
  shrinks and fades while it is in the air.
- **Simpler menu.** Removed Good night, Good morning, Talk to me and "Music is playing". The bird now keeps its own
  body clock instead: it gets sleepy around 21:30-22:00 and sleeps on its own, even with the room lit.
- **Sleep deprivation.** Kept awake past bedtime, or woken again and again, the bird builds up sleep debt and becomes
  grumpy: easily frustrated, quicker to anger, less happy and playful. Treats do not fix it; only sleep does.
- **New mood panel.** Its own small window that can be dragged anywhere: hunger and sleep-deprived meters with plain
  words, twelve feelings in a fixed order, what the bird is doing, bond and mood. Readable at a glance.
- **Sound matches the beak.** Every call opens the beak visibly (lip-sync at least 22°). No calls while the beak is
  busy or hidden (being scratched, asleep, eating, preening). The head-scratch clip's beak-grinding noise is gone.
- **The head scratch ends when your hand leaves the head.** It used to linger for about 7 s while the cursor was
  already on the belly; now it ends within about 1 s.
- **Windows and macOS.** New OS layer (click-through, idle time, data folders, tool windows on macOS), run scripts
  for both systems, a PyInstaller recipe for a Windows exe folder and a macOS `.app`, and a GitHub Actions workflow
  that tests and builds both and attaches them to tagged releases.
- **Documentation** for users (install, user guide) and developers (architecture, adding a pet, building, publishing).
- Tests: 24 unit tests (was 15); review sheets for flight, the panel and the beak.

## 0.3.0 - 2026-10-29

- Emotions reworked (engine v4): moving the cursor never makes the bird angry; only clicking does. An appraisal
  layer judges what the hand is doing (gentle → happy/playful, resting close → curious, on the head → relaxed,
  frantic scrubbing → a bit annoyed). Every left click is a poke and clicks add up. Petting, head touch and food make
  anger fade much faster; a poke cuts through a cuddle.
- Menu: Pet (head scratch) and Poke.
- Fixed: the head popping back to neutral for a few frames during the head scratch; eye and lid flicker when standing
  on one leg (the procedural layer reset held poses to rest); pupil pinning flicker; the bird leaving and re-entering
  the scratch pose between strokes.
- Tools: `app.trace` (per-frame rig trace), eye close-up review, 26 interaction rules as tests.

## 0.2.0 - 2026-10-27

- The tree branch is gone; the bird stands on its own feet with a soft contact shadow.
- Body turns ±30° towards the cursor; head, neck and eyes track it. Blinks, lid droop, pupil pinning, jaw lip-sync.
- Sizes Small / Medium / Large.
- Petting redesigned (hover = scratch, zone-aware clicks).
- Smoother animation, click-through on transparent pixels, tray icon, plugin checker, visual review harness.

## 0.1.0 - 2026-10-27

- First build: the V10 sun conure model with 72 animations, the ConureMind emotion engine, the sound bank and 2D
  mood effects in a species-pluggable desktop app.
