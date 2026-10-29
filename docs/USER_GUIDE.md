# User guide

## Meet the bird

The sun conure stands on your desktop, by default at the bottom-right just above the taskbar. It is a 3D animal with
moods, needs and a memory. It is not a looping animation: what it does next depends on how it feels, what it needs
and what you do.

It keeps living while you work. It preens, stretches, looks around, plays, calls for you when it feels ignored, asks
for food, dozes, and sleeps at night. Clicks on the empty space around it go straight through to whatever is
underneath, so it never gets in your way.

## Touching it: petting and poking

| You do | It feels | You see |
|---|---|---|
| Move the mouse normally, even right across the bird | Friendly, playful | Watches the cursor, head bobs, tail wags |
| Hold the cursor still near it | Curious | Peeks, tilts its head, walks over, asks for a scratch |
| Rest the cursor on its head | Relaxed | Eyes droop, leans in |
| **Move the cursor up and down over its head** | **Loves it** | **Head-scratch pose**, eyes half-closed, hearts |
| Move from its head down to its belly | The scratch has stopped | Leaves the scratch pose within about a second |
| Scrub wildly right on top of it | A bit annoyed | Leans back, turns away, one annoyed mark |
| **Left-click it** | **Poked**: a bit angry | Grumbles, anger mark, leans back or puffs up. The belly annoys it most. |
| Click again and again | Very angry | Full anger display, warning lunges |
| Pet it or give it a treat after that | Calms down | Anger fades within a few seconds |
| Press and drag | Carried | Moves with your mouse; stays where you drop it |

Rules worth knowing:
- **Moving the cursor never makes it really angry.** Only clicking does.
- Right-clicking is never a poke. It only opens the menu.
- It learns: a bird that is often scratched comes to you happily; a bird that is often poked becomes wary of the
  cursor for a while, and scratching retrains it.
- Scratches are best on the head and neck. Over-petting is never unpleasant; it just gets enough and moves on.

## The right-click menu

| Item | What it does |
|---|---|
| *(top line)* | The bird's name and its main mood right now |
| **Pet (head scratch)** | A six-second head scratch without moving the mouse |
| **Poke** | One poke in the belly (it gets a bit angry) |
| **Offer a sunflower seed** | Its favourite: it gets excited, takes it, cracks it. Fills hunger a lot and calms anger. |
| **Offer millet** | A smaller snack: pecks and nibbles |
| **Play** | Invites play: it gets playful (dances, crouches, wing displays) |
| **Fly** | Takes off, hovers for a few seconds and lands |
| **Size** | Small (default) / Medium / Large. The feet stay where they are. |
| **Look** | Female / male (the female has eyelashes) |
| **Sound** | Mute; volume Quiet / Normal / Loud; "Quieter when I am away" (8 dB quieter after 5 minutes without input) |
| **Mood panel** | Shows or hides the mood panel window (below) |
| **Hide** | Hides the bird; click the tray / menu-bar icon to bring it back |
| **Quit** | Saves its memory and closes the app |

"Pet", "Poke", "Play" and "Fly" are only offered while it is awake.

## The mood panel

A small window of its own: drag it anywhere, close it with ×. It remembers where you put it and whether it was open.

- **Top line:** its main mood in colour, then what it is doing ("enjoying a head scratch", "asking for food",
  "dozing", ...).
- **Needs**
  - **Hunger:** rises over a few hours awake (slower asleep). A sunflower seed takes most of it away, millet a
    little. The bird also has a bowl you cannot see, so it never starves: the meter is its appetite for treats.
    *Full → Peckish → Hungry → Very hungry.*
  - **Sleep-deprived:** lost sleep (below). *Well rested → A bit tired → Grumpy → Exhausted.*
- **Feelings:** twelve bars in a fixed order: happy, playful, affectionate, relaxed, curious, excited, sleepy, hungry,
  frustrated, angry, scared, sad. Several can be active at once, as in a real animal. The values are smoothed so the
  bars move calmly.
- **Bottom:** bond (how much it trusts you, grows with good treatment) and overall mood (the last half hour, from
  negative to positive).

## Sleep, bedtime and grumpiness

The bird has its own body clock. It gets sleepy in the evening and sleeps at night. With the room lit and you still
at the computer it may stay up a little longer, but from about 21:30-22:00 it wants to sleep. It also naps during the
day when it is tired.

**If you keep it awake** - petting it, clicking it, feeding it or making it fly late in the evening, or waking it up
again and again - it builds up **sleep debt** ("Sleep-deprived" in the panel). A sleep-deprived bird is grumpy:

- easily frustrated, quicker to get angry when poked, grumbles to itself;
- less happy and less playful;
- **a treat does not fix it**: it eats, but stays cranky. Only sleep does.

To help it: leave it alone in the evening. It falls asleep on its own (Zzz). About an hour of real sleep repays most
of the debt, and it also recovers while the app is closed.

## Its memory

When you quit (and every minute) it saves its long-term state: hunger, sleep pressure and sleep debt, needs, mood,
bond with you, what your cursor usually means (scratches or pokes), when it usually gets food, and whether the menu
tends to mean food. When you start the app again it catches up on the time that passed (up to 24 hours): it got
hungrier, slept, missed you, and greets you after a long absence.

It never stores cursor positions, keystrokes, screen content or anything about your computer. To make it forget
everything, quit and delete `pets/sun_conure/state.json` in the data folder (see [INSTALL.md](INSTALL.md)).

## Little effects

Hearts and sparkles (affection, a scratch), music notes (singing and chirping), smoke puffs and an anger mark
(angry), Zzz (asleep), `!` (startled), `?` (curious), sweat drops (scared), a rain cloud and tears (sad), green
leaves and petals (playing), dry leaves (bored or lonely), call rings (calling for you).
