# sounds/ - optional sound bank of your pet

Put here (all optional; a pet without sounds is silent):

- `sound_bank.json` - categories (calls, chirps, wing flaps, ...), which files belong to each, loudness, and which
  sounds are mouth sounds (those must move the beak - see `pet.json` > `sounds` > `min_jaw_deg` and `quiet_clips`).
- `bank/*.wav` - the sound files.
- `CREDITS.md` - source and licence of every recording. Required before you publish the pet.

Full reference: [docs/ADDING_A_PET.md](../../../docs/ADDING_A_PET.md). The sun conure (`pets/sun_conure/sounds/`) is a
complete example.
