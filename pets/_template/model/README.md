# model/ - the 3D model of your pet

Put here (names must match `pet.json` > `model`):

- `<variant>.glb` - one rigged glTF binary per look (e.g. `pet.glb`, or `female.glb` + `male.glb`). All variants share
  one skeleton and the same baked animation clips.
- `animations.json` - the clip table: name, duration, loop flag and timed events for every baked clip
  (`pet.json` > `model` > `clips`).

Bone, jaw, eyelid and pupil names the web player needs are listed in `pet.json` > `rig`. Full reference:
[docs/ADDING_A_PET.md](../../../docs/ADDING_A_PET.md). The sun conure (`pets/sun_conure/model/`) is a complete example.
