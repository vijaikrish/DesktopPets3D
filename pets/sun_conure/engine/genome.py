"""ConureMind genome: the wiring of the sun conure's emotion network (pure data, no code).

Like the 'genome' of Creatures' norns, this file defines every neuron, connection weight, time constant and
behaviour of the bird. conure_mind.py turns it into matrices and runs it. Edit numbers here, not in code.

Units: time constants in seconds of real time unless marked _h (hours). Weights act on net input (sigmoid
neurons: net -3 -> 0.05 activation, 0 -> 0.5, +3 -> 0.95). Features and emotions are 0..1.

Research basis (summary; full list in REFERENCES):
- Core affect = valence x arousal (Russell 1980; Mendl, Burman & Paul 2010 for animals); mood = running mean of
  core affect that biases how ambiguous events are read (optimistic / pessimistic cognitive bias).
- Primary emotion systems SEEKING, RAGE, FEAR, CARE, PANIC/GRIEF, PLAY (Panksepp; birds have homologous systems).
- Drives as homeostatic needs pushing the emotion system (Kismet: social, stimulation, fatigue - Breazeal 2003).
- Neural net + artificial biochemistry for a virtual pet (Creatures - Grand, Cliff & Malhotra 1997).
- Action-specific energy that builds up and is discharged by acting (Lorenz) + ethological action selection
  with persistence and 'level of interest' (Blumberg 1996).
- Sleep = homeostatic pressure S + circadian/light C (Borbely two-process model); parrots show a morning and a
  late-afternoon activity peak with a midday rest (van Zeeland et al. 2023; Rozek & Millam 2011).
- Parrot body language: eye pinning = strong excitement (good or bad); tail fanning = high excitement /
  aggression; crest up = alert/excited, flat = fear; fluffed + beak grinding + one foot = relaxed; lowered fluffed
  head = 'scratch me'; fluff + quick shake + tail wag = greeting the loved one; sleeked, tall, frozen, leaning
  away = fear; head bobbing + wings slightly out = courtship / bonding (Lafeber vet; Parrot Fun Zone; Bertin
  et al. 2018: crown ruffling & blushing during positive low-arousal contact with a familiar caretaker).
- Sun conure: extremely social flock bird; loud contact call (3-6 shrieks) when separated; quiet while eating;
  playful 'clown'; strong bond with its person.
- Personality: neuroticism and extraversion explain 66 % of personality variance in Amazon parrots and predict
  attention bias (Cussen & Mench 2014).
- Conditioning: Rescorla-Wagner delta rule (= a single-layer neural net) for cue -> outcome expectations;
  habituation of repeated harmless startles (Thompson & Spencer 1966); frustration when an expected reward is
  omitted (Amsel). Emotional contagion of play in kea (Schwing et al. 2017) -> music/play invites play.
"""

# ----------------------------------------------------------------------------- input layer (features)
# Computed every tick by conure_mind._features() from percepts, drives, event traces, learning and mood.
FEATURES = [
    'hunger', 'sleep_drive', 'social_need', 'boredom', 'groom_need', 'stress',          # body / drives
    'present', 'alone', 'cursor_near', 'cursor_fast', 'approach', 'attention', 'looming',  # senses
    'petting', 'poke', 'held', 'reward_sun', 'reward_mil', 'offer', 'music', 'novelty',  # events / traces
    'talk', 'play_inv', 'reunion', 'sudden', 'night', 'just_woke',
    'exp_food', 'exp_pet', 'exp_poke', 'bond',                                          # learned
    'mood_pos', 'mood_neg', 'amb_pos', 'amb_neg', 'unanswered', 'social_seek', 'disturb_sleep',
    'touch_need', 'pet_bad', 'hand_good', 'hand_bad', 'hand_sad', 'neglect',              # touch & the hand (v2)
    'cursor_gentle', 'cursor_still', 'head_touch', 'irritation', 'annoyed', 'comfort',   # appraisal layer (v4)
    'sleep_debt',                                                                       # v5: lost sleep
]

# ----------------------------------------------------------------------------- appraisal layer (v4)
# A small hand-wired layer between the raw cursor percepts and the emotion network: it judges WHAT the hand is doing,
# not just where it is. Units (0..1, leaky integrators):
#   cursor_gentle  slow-to-normal movement within ~2.5 bird heights  -> a moving 'toy' / friendly presence: happy, playful
#                  (habituates over minutes of constant movement, like any novelty)
#   cursor_still   the cursor resting close by                          -> curious (head tilts, peering)
#   head_touch     the cursor resting on / gently moving over the head  -> relaxes (content, lids droop, comfort)
#   irritation     frantic scrubbing right on top of the bird            -> 'a bit' annoyed; capped by construction
#   comfort        affiliative-touch / food neuromodulator (mesotocin- and opioid-like) -> calms (see NEUROMOD)
# Truthfulness: in parrots, anger (RAGE) answers a physical provocation; a hand that is merely present or moving is
# investigated (curiosity) or, for a tame bird, welcomed. Social buffering: an affiliative partner mitigates stress
# responses, more so with a close bond (Kiyokawa & Hennessy 2018); gentle touch (allopreening) is how pair bonds are
# kept (Kenny et al. 2017); food is the companion parrot's main positive reinforcer (Friedman).
APPRAISAL = dict(
    gentle_radius_px=400.0,          # ref px (160 px bird): cursor_gentle fades out beyond this
    gentle_speed=(30.0, 120.0, 1400.0, 2600.0),   # px/s: rises 30..120, full up to 1400, gone by 2600
    still_speed=(20.0, 150.0),       # px/s: below 20 = still, above 150 = moving
    # Real mouse figures (S = 130 px bird; ref px = screen px x 160 / 130): a gentle up-down scratch is 30-60 px at
    # 1-2 Hz = 120-480 px/s and 2-4 reversals/s; a frantic scrub is 40-80 px at 4-6 Hz = 650-1900 px/s, 8-12 reversals/s.
    frantic_speed=(1200.0, 2200.0),  # ref px/s: frantic only if this fast (beyond a vigorous scratch) ...
    frantic_jitter=(4.0, 8.0),       # ... AND this jittery (direction reversals per second) ...
    frantic_close=(0.45, 0.85),      # ... AND this close (cursor_near = exp(-d / 250 px): 0.45 ~ 200 px, 0.85 ~ 40 px)
    irritation_rate=0.8,             # per second of fully frantic motion (trace tau 4 s)
    frantic_drain=2.0,               # comfort decays at this rate (1/s) x frantic: a scrubbing hand is not soothing
    head_zones=('head', 'crown', 'nape', 'cheek', 'neck'),
    head_still_max=900.0,            # px/s: a hand on the head moving slower than this counts as touching it
    comfort_head=0.15,               # comfort per second of head_touch
    comfort_pet=0.35,                # comfort per good stroke (x quality)
    comfort_food=1.0,
    scratch_gap_s=1.2,               # v5: no good head stroke for this long and the hand is off the head -> scratch over
    gentle_habituation_s=(300.0, 600.0),   # build-up / recovery of habituation to constant cursor play
    gentle_habituation_max=0.6,
)

# Neuromodulation (v4): a modulator shortens the DECAY time constant of its target neurons,
# tau_eff = tau / (1 + sum_m k_m x level_m).
#   comfort      (petting, head touch, food)         -> anger / fear / frustration let go several times faster
#   provocation  (clicks: poke + pet_bad + startle)   -> a poke breaks a calm, happy state at once (contentment
#                                                      otherwise fades over ~40 s and would mask the poke)
NEUROMOD = dict(comfort=dict(angry=2.5, frustrated=2.5, afraid=2.5, startled=1.0, sad=1.0),
                provocation=dict(content=6.0, affectionate=4.0, sleepy=3.0, happy=2.0, playful=2.0))

# ----------------------------------------------------------------------------- emotion layer (CTRNN)
# V = valence, A = arousal, S = stance (+approach / -withdraw) of each emotion in core-affect space.
# rise = onset time constant (s, fast attack), tau = decay time constant (s, slow release); bias = resting net input; self = self-excitation (persistence);
# noise = OU noise sigma on the net input (spontaneous mood drift); inputs / inhibit = weights.
EMOTIONS = {
    'content': dict(V=0.5, A=0.2, S=0.1, tau=40, rise=10, bias=-0.8, self=1.5, noise=0.55,
                    system='homeostatic satiety', signs='fluffed, beak grinding, one foot up, slow blinks',
                    inputs=dict(present=0.8, bond=0.8, mood_pos=1.5, reward_sun=1.0, reward_mil=1.0, petting=1.0,
                                sleep_drive=0.6, hunger=-2.0, social_need=-1.5, boredom=-1.0, stress=-3.0,
                                cursor_fast=-1.0, poke=-2.5, looming=-1.5, pet_bad=-2.0, touch_need=-0.8,
                                head_touch=2.0, comfort=1.5, cursor_gentle=0.4, irritation=-1.0, sleep_debt=-1.0),
                    inhibit=dict(angry=2.0, afraid=2.5, startled=2.0, frustrated=1.5, lonely=1.5, hungry=1.0)),
    'happy': dict(V=0.75, A=0.6, S=0.5, tau=12, rise=0.8, bias=-3.2, self=1.0, noise=0.5,
                  system='SEEKING/PLAY joy', signs='tail wag, bouncing, fluff-and-shake, chirps',
                  inputs=dict(reward_sun=3.5, reward_mil=1.0, petting=1.8, talk=1.5, reunion=3.0, play_inv=1.5,
                              music=1.5, mood_pos=1.5, bond=0.8, attention=0.8, stress=-2.5, sleep_drive=-1.5,
                              hunger=-0.8, social_need=-1.0, poke=-3.0, night=-1.0, hand_good=1.0, pet_bad=-2.0,
                              cursor_gentle=1.8, comfort=0.8, head_touch=0.6, irritation=-1.0, sleep_debt=-1.5),
                  inhibit=dict(sad=2.0, afraid=2.0, angry=2.0, startled=1.5)),
    'playful': dict(V=0.6, A=0.8, S=0.6, tau=15, rise=2, bias=-2.9, self=1.0, noise=0.6,
                    system='PLAY', signs='leaning forward with wings out, play-biting, rocking, clowning',
                    inputs=dict(boredom=1.2, play_inv=3.0, music=1.5, amb_pos=2.0, mood_pos=1.2, attention=0.8,
                                sleep_drive=-2.5, hunger=-1.0, stress=-2.5, night=-2.0, poke=-2.5,
                                cursor_gentle=2.2, irritation=-1.0, pet_bad=-1.5, sleep_debt=-2.0),
                    inhibit=dict(afraid=3.0, sad=2.0, angry=1.0, sleepy=1.5)),
    'affectionate': dict(V=0.8, A=0.35, S=0.7, tau=25, rise=3, bias=-3.6, self=1.2, noise=0.5,
                         system='CARE / bonding (mesotocin)', signs='lowered fluffed head, slow blinks, head bob',
                         inputs=dict(bond=2.0, attention=1.2, petting=2.5, exp_pet=1.5, social_seek=1.0,
                                     mood_pos=0.8, sleep_drive=0.4, stress=-2.5, poke=-3.0, cursor_fast=-1.0,
                                     exp_poke=-2.0, touch_need=1.5, hand_good=1.5, pet_bad=-2.5,
                                     head_touch=1.5, comfort=1.0, sleep_debt=-0.8),
                         inhibit=dict(angry=2.0, afraid=2.5, playful=0.5)),
    'curious': dict(V=0.3, A=0.55, S=0.6, tau=8, rise=0.8, bias=-2.6, self=0.5, noise=0.6,
                    system='SEEKING (explore)', signs='head tilts, one-eye look, crest up, peering',
                    inputs=dict(novelty=3.0, approach=2.5, boredom=0.8, attention=0.6, amb_pos=0.8, offer=1.0,
                                talk=0.8, sleep_drive=-2.0, stress=-1.0,
                                cursor_still=2.5, cursor_gentle=0.6, hand_bad=0.8,      # v4: a hand close by = curiosity
                                sleep_debt=-0.8),
                    inhibit=dict(afraid=1.5, sleepy=1.0)),
    'excited': dict(V=0.6, A=0.9, S=0.7, tau=5, rise=0.5, bias=-3.5, self=0.8, noise=0.5,
                    system='SEEKING (reward anticipation)', signs='eye pinning, crest up, tail spread, flutter',
                    inputs=dict(offer=3.5, exp_food=2.5, reunion=2.0, music=1.0, play_inv=1.5, reward_sun=1.5,
                                sleep_drive=-2.0, hand_good=2.5),
                    inhibit=dict(sleepy=2.0, sad=1.5)),
    'proud': dict(V=0.5, A=0.75, S=0.8, tau=15, rise=2, bias=-3.4, self=1.0, noise=0.5,
                  system='display', signs='eye pinning, tail fanned, wings stiff from the shoulders, strutting',
                  inputs=dict(attention=1.5, mood_pos=1.5, bond=0.5, music=1.0, stress=-2.0, sleep_drive=-2.0,
                              hunger=-1.0),
                  inhibit=dict(afraid=2.0, sad=2.0)),
    'hungry': dict(V=-0.1, A=0.6, S=0.6, tau=20, rise=3, bias=-4.2, self=0.5, noise=0.4,
                   system='SEEKING (homeostatic hunger)', signs='begging, knocking, pinning at food',
                   inputs=dict(hunger=5.0, exp_food=1.5, offer=2.0, reward_sun=-4.0, reward_mil=-2.5,
                               sleep_drive=-1.0),
                   inhibit=dict(afraid=1.5, sleepy=1.0)),
    'lonely': dict(V=-0.5, A=0.65, S=0.4, tau=30, rise=8, bias=-3.6, self=1.0, noise=0.4,
                   system='PANIC/GRIEF (separation distress)', signs='loud contact calls, searching, pacing',
                   inputs=dict(social_need=4.5, alone=1.5, bond=0.8, petting=-3.0, talk=-2.0, attention=-2.5,
                               sleep_drive=-2.0, reunion=-3.0, night=-4.0, touch_need=0.4, neglect=0.6),
                   inhibit=dict(happy=1.0, sleepy=1.5)),
    'bored': dict(V=-0.3, A=0.15, S=0.0, tau=60, rise=20, bias=-3.0, self=1.0, noise=0.5,
                  system='low SEEKING (under-stimulation)', signs='sighs, slumped, yawning, over-preening',
                  inputs=dict(boredom=4.0, alone=0.5, novelty=-3.0, play_inv=-3.0),
                  inhibit=dict(curious=1.5, playful=2.0, excited=2.0)),
    'frustrated': dict(V=-0.5, A=0.7, S=0.3, tau=20, rise=3, bias=-3.5, self=1.0, noise=0.4,
                       system='RAGE (mild, blocked goal / omitted reward)', signs='pacing, tail flicks, beak wiping',
                       inputs=dict(unanswered=4.0, poke=1.0, held=0.5, boredom=0.8, petting=-2.0, reward_sun=-2.0,
                                   reward_mil=-1.5, pet_bad=1.5, neglect=0.5, irritation=1.0, comfort=-2.0, offer=-1.0,
                                   sleep_debt=3.6),                  # v5: an over-tired bird is cranky (husbandry)
                       inhibit=dict(content=1.0)),
    'angry': dict(V=-0.7, A=0.85, S=0.6, tau=10, rise=0.6, bias=-4.0, self=1.0, noise=0.4,
                  system='RAGE', signs='pinned eyes, hackles, tail fan, open-beak lunge',
                  # v4: RAGE answers provocation only = clicks (poke, pet_bad). The cursor can at most irritate
                  # (irritation, capped); a nearby or bad-reputation hand makes the bird wary/curious, never angry.
                  inputs=dict(poke=5.0, held=0.5, bond=-0.5, stress=1.5, disturb_sleep=2.5, mood_neg=1.0,
                              petting=-2.0, pet_bad=4.0, irritation=3.0, comfort=-3.0, head_touch=-1.5,
                              reward_sun=-3.0, reward_mil=-2.0, offer=-2.0,
                              sleep_debt=1.8),                  # v5: grumpy when kept awake - and quicker to anger
                  inhibit=dict(afraid=1.5, content=0.5)),     # v4: 0.5 (was 1.0) - even a content bird feels a poke
    'afraid': dict(V=-0.7, A=0.8, S=-0.8, tau=12, rise=0.5, bias=-4.0, self=1.2, noise=0.4,
                   system='FEAR', signs='sleeked, tall, crest flat, frozen stare, leaning away',
                   inputs=dict(stress=3.0, held=2.5, bond=-1.5, amb_neg=2.5, looming=2.5, exp_poke=2.0,
                               petting=-1.5, hand_bad=1.8, comfort=-2.0, head_touch=-1.5),   # v4: a poking hand -> wary, not angry
                   inhibit=dict(content=1.5, angry=1.0)),
    'startled': dict(V=-0.3, A=1.0, S=-0.5, tau=0.4, rise=0.1, bias=-5.0, self=0.0, noise=0.0,
                     system='FEAR (startle reflex)', signs='flinch, wing flick, freeze',
                     inputs=dict(sudden=9.0), inhibit=dict()),
    'sad': dict(V=-0.7, A=0.2, S=-0.4, tau=300, rise=6, bias=-4.5, self=1.5, noise=0.4,
                system='PANIC/GRIEF (low)', signs='drooped, head low, turned away',
                inputs=dict(mood_neg=2.0, social_need=1.0, reunion=-4.0, petting=-3.0, reward_sun=-2.0,
                            hand_sad=3.5, neglect=1.5, comfort=-1.5),
                inhibit=dict(happy=2.0, playful=1.0)),
    'sleepy': dict(V=0.0, A=0.05, S=-0.2, tau=60, rise=20, bias=-3.5, self=1.0, noise=0.4,
                   system='homeostatic sleep pressure', signs='half-closed eyes, one foot up, fluffed, grinding',
                   inputs=dict(sleep_drive=6.0, night=1.5, stress=-3.0, novelty=-1.5, hunger=-1.0,
                               attention=-0.5, cursor_gentle=-1.0, sleep_debt=1.5),   # v5: activity keeps it up
                   inhibit=dict(startled=4.0, excited=2.0, afraid=2.0)),
    'mischievous': dict(V=0.4, A=0.7, S=0.6, tau=15, rise=2, bias=-3.5, self=1.0, noise=0.6,
                        system='PLAY (teasing)', signs='sneaky look, wink, clowning to get a reaction',
                        inputs=dict(boredom=1.0, attention=1.0, mood_pos=0.8, stress=-2.0, sleep_drive=-2.0),
                        inhibit=dict(afraid=2.0, sad=2.0)),
}

# Recurrent emotion -> emotion excitation (beyond 'self' and 'inhibit'): emotions that feed each other.
EXCITE = {
    ('playful', 'happy'): 1.0, ('happy', 'playful'): 0.5, ('mischievous', 'playful'): 1.5,
    ('proud', 'happy'): 1.2, ('excited', 'happy'): 0.8, ('afraid', 'startled'): 2.0,
    ('angry', 'frustrated'): 0.8, ('sad', 'lonely'): 1.2, ('sad', 'frustrated'): 1.0,
    ('frustrated', 'hungry'): 0.5, ('frustrated', 'lonely'): 0.5, ('content', 'sleepy'): 0.5,
    ('affectionate', 'content'): 0.5,
}

# Personality traits (0..1) and how they shift emotion biases (+-1 * weight * (trait - 0.5) * 2).
PERSONALITY = dict(neuroticism=0.25, extraversion=0.8, playfulness=0.85, volatility=1.0)   # v4: a playful, easy-going bird
PERSONALITY_EFFECTS = {
    'neuroticism': dict(afraid=1.5, startled=1.0, frustrated=0.8, sad=0.5, content=-0.5, curious=-0.5),
    'extraversion': dict(lonely=0.6, proud=0.8, happy=0.4, playful=0.3, bored=0.4),
    'playfulness': dict(playful=1.0, mischievous=0.8, curious=0.3),
}

# ----------------------------------------------------------------------------- body (artificial biochemistry)
DRIVES = dict(
    hunger_rise_h=3.0,          # hunger -> 63 % of the way to 1 in 3 h awake (x0.3 asleep)
    hunger_bowl=0.5,            # above this the bird feeds itself from its (unseen) bowl (treat appetite)
    food=dict(sunflower=0.45, millet=0.12, millet_nibble=0.05),
    sleep_rise_h=16.0,          # Borbely process S while awake
    sleep_fall_h=3.5,           # ... while asleep
    social_rise_min=35.0,       # alone; x (1.5 - extraversion); x3 slower when the user is present
    social_fill_s=90.0,         # attention (cursor near and calm) fills the social need
    boredom_rise_min=20.0,
    groom_rise_min=30.0,        # grooming need; each preening clip discharges a little -> bouts, ~10 % budget
    stress_decay_min=5.0,       # corticosterone half-life-ish; x (1 + neuroticism)
    mood_tau_min=30.0,          # mood = running mean of core affect
    touch_rise_min=90.0,        # need for physical affection (head scratches) awake; x 1 / (0.5 + bond)
    neglect_rise_min=20.0,      # 'ignored while my person is here': builds while the touch need stays unmet
    neglect_decay_min=60.0,
)

# ----------------------------------------------------------------------------- sleep debt (v5)
# Vijai: "if I keep the bird awake, it gets sleep deprived and gets grumpy, even if I feed the food".
# Companion parrots need ~10-12 h of dark, quiet sleep; birds kept up late by lights and household activity become
# irritable, noisy and nippy (avian husbandry guidance - PetMD, Merck Vet Manual; practice advice, not a controlled
# study). In people one night without sleep raises amygdala reactivity to negative stimuli by ~60 % and weakens its
# prefrontal control (Yoo et al. 2007) - modelled here as amplified provocation and blunted soothing.
#   pressure   = clamp(1.25 S + 0.85 max(night, bio_night x lamp_night) - 0.5)   (no stress / debt terms)
#   awake:     debt += (1 - debt) x clamp((pressure - threshold) / span) x dt / rise_h
#   asleep:    debt *= exp(-dt / recover_h)   (dozing: recover_doze_h; in a lit room x lit_factor slower)
#   woken up while sleep pressure is high: debt += wake_penalty x pressure
#   effects:   feature 'sleep_debt' -> frustrated +3.6, angry +1.8, sleepy +1.5, happy/playful/... down;
#              provocation features x (1 + amplify x debt); comfort, treats and offers x (1 - blunt x debt)
#              -> a treat no longer fixes the mood: only sleep does.
SLEEP_DEBT = dict(
    bio_night=(21.0, 22.5, 6.0, 7.5),   # the bird's own clock: night ramps up 21:00-22:30, down 06:00-07:30
    lamp_night=0.6,                     # under the room lamp the bird still feels it is night, at 60 %
    threshold=0.45, span=0.45,          # sleep pressure above which staying awake costs sleep
    rise_h=1.0,                         # ~1 h kept up past bedtime -> 63 % sleep-deprived
    recover_h=1.0,                      # real sleep repays the debt quickly
    recover_doze_h=4.0,
    lit_factor=0.6,                     # sleeping under the lamp recovers at 60 % of the rate
    away_recover_h=3.0,                 # app closed: assume the bird slept
    wake_penalty=0.06,                  # each time it is woken up while still sleepy
    amplify=0.8,                        # provocation (clicks, scrubbing) x (1 + 0.8 debt)
    blunt=0.85,                         # comfort, treats, offers x (1 - 0.85 debt)
    drive_gain=0.5,                     # sleep_drive += 0.5 debt (an over-tired bird naps more readily)
)

# ----------------------------------------------------------------------------- flight (v5, menu 'Fly')
# flap_takeoff is a 3 s bake: take-off 0-0.8 s, airborne 0.8-2.2 s (exactly periodic, 1.0 s = 3 wing beats,
# pose distance 0 between t and t+1), landing 2.2-3.0 s. The hover is extended by looping [1.0, 2.0] 'repeats'
# times (engine clip time and the web player warp the same way), so a flight is 3 + repeats seconds.
FLY = dict(clip='flap_takeoff', loop=(1.0, 2.0), repeats=2,
           lift_scale=1.9)    # web player: the bird rises 1.9x the baked root lift (~0.4 bird heights)

# ----------------------------------------------------------------------------- petting (v2)
# The app sends event('pet', zone=..., speed=px/s) a few times per second while the user strokes the bird.
# quality q (-1..1) = zone x stroke speed - over-petting - not in the mood. q > 0 -> pleasure (petting trace,
# touch need filled, bond up, the hand becomes a good sign); q < 0 -> 'pet_bad' (annoyed / angry, the hand
# becomes a bad sign). Lafeber: limit petting to head and neck; tail, lower back and below the chest are
# hormonal 'hot spots'; stroke gently against the grain, rub cheeks in small circles. Over-stimulation and
# ignored warning signs (pinned eyes, fanned tail, lunging) lead to bites.
# v4: hovering is NEVER unpleasant. Head and neck = petting; elsewhere the hand is tolerated (small or zero value).
# Unwelcome touch is a CLICK (TAP). Too fast = less pleasant down to 0 (frantic scrubbing -> APPRAISAL irritation);
# too long = satiation (pleasure fades to 0 and the bird turns to something else), not pain.
PETTING = dict(
    zones=dict(head=1.0, crown=1.0, nape=1.0, cheek=0.9, neck=0.85, beak=0.1, chest=0.3, back=0.2,
               wing=0.15, belly=0.0, tail=0.0, feet=0.0),
    # v3 (DesktopPets3D): a stroke is the mouse cursor wiggling over the bird (no button). Speeds are normalised by
    # the adapter to a 160 px tall bird; a relaxed mouse 'scratch' is 150-650 px/s, a hard rub > 1000 px/s.
    speed_good=(30.0, 1000.0),  # px/s: gentle..vigorous mouse scratching (v4); slower = barely felt
    speed_rough=1600.0,         # px/s at which a stroke gives no pleasure any more (v4: frantic territory)
    dose_tau_s=150.0,           # how long a petting session is 'remembered' for over-stimulation
    tolerance_s=70.0,           # petting seconds before it starts to be too much (x (0.4 + touch need + bond / 2))
    upset_share=0.6,            # an upset bird gets less pleasure from a stroke; that share calms it instead
    soothe=dict(pet_bad=0.12, poke=0.06, irritate=0.20, stress=0.02),   # fraction removed per stroke at quality 1
)

# A left click on the bird (v4): ALWAYS a poke - head included (Vijai: 'clicking is the only option to trigger
# anger'). 'annoy' feeds the pet_bad trace (-> angry, avoid_hand / threaten) and, through poke_gain, the poke trace,
# so repeated clicks escalate from 'a bit angry' to really angry. 'startle' feeds the sudden trace. Belly, tail and
# lower back are the hormonal hot spots owners are told not to touch (Lafeber), so they annoy most.
TAP = dict(
    poke_gain=0.25,
    zones=dict(head=dict(annoy=0.95, startle=0.35, sound='grumble'), crown=dict(annoy=0.95, startle=0.35, sound='grumble'),
               nape=dict(annoy=0.95, startle=0.35, sound='grumble'), cheek=dict(annoy=0.95, startle=0.35, sound='click'),
               neck=dict(annoy=0.95, startle=0.35, sound='grumble'),
               beak=dict(annoy=1.0, startle=0.3, sound='click'),
               chest=dict(annoy=1.0, startle=0.3, sound='grumble'),
               belly=dict(annoy=1.1, startle=0.3, sound='grumble'),
               wing=dict(annoy=1.0, startle=0.45, sound='grumble'),
               back=dict(annoy=0.95, startle=0.5, sound='grumble'),
               tail=dict(annoy=1.05, startle=0.45, sound='grumble'),
               feet=dict(annoy=1.0, startle=0.35, sound='click')),
    default=dict(annoy=1.0, startle=0.4, sound='grumble'),
)
# Right-click menu actions (v4): 'Pet' = a hand-free head-scratch session of this length; 'Poke' = one poke here.
MENU_TOUCH = dict(pet_session_s=6.0, pet_speed=320.0, poke_zone='belly')

# ----------------------------------------------------------------------------- behaviour layer
# Each behaviour: bias, emotion weights, feature weights, gates ('requires' = minimum values), how fast the
# bird loses interest while doing it (interest_tau s), persistence bonus, priority rank (1-3: may interrupt the
# clip that is playing; a higher rank overrides the current behaviour's persistence), effects on drives (rate per MINUTE spent doing it), and the clips it can play.
# Clip entry: (clip, weight) or (clip, weight, {name: (lo, hi)}) - the clip is only eligible when those
# emotions/features are inside [lo, hi].
BEHAVIOURS = {
    'rest': dict(bias=0.6, emotions=dict(content=1.5, sleepy=0.4),
                 features=dict(novelty=-0.5, night=-2.0, attention=-0.5, head_touch=1.5),
                 interest_tau=180,
                 clips=[('idle_breathe', 3), ('wing_idle', 2), ('tail_bob', 1),
                        ('beak_grind', 1.5, {'content': (0.45, 1), 'sleepy': (0.2, 1)}),
                        ('rest_one_leg', 1.5, {'content': (0.4, 1)})]),
    'look_around': dict(bias=0.2, emotions=dict(curious=0.8, bored=0.3, afraid=0.6), interest_tau=40,
                        clips=[('idle_look_around', 3), ('curious_tilt', 1)]),
    'watch_user': dict(bias=-0.5, emotions=dict(curious=1.0, affectionate=0.8),
                       features=dict(attention=2.0, cursor_gentle=1.5, cursor_still=1.0),
                       requires=dict(present=0.3), interest_tau=40,
                       clips=[('curious_tilt', 2), ('curious_peek', 1.5), ('idle_breathe', 1)]),
    'investigate': dict(bias=-1.0, emotions=dict(curious=2.0), features=dict(novelty=1.0, cursor_still=1.0),
                        requires=dict(curious=0.3),
                        interest_tau=25,
                        clips=[('curious_full', 2), ('curious_peek', 1),
                               ('wary_lean_back', 1.5, {'afraid': (0.15, 1)}),
                               ('wary_lean_back', 2.0, {'hand_bad': (0.3, 1)}),   # v4: curious but cautious of a poking hand
                               ('walk_to_screen', 0.5, {'cursor_near': (0.3, 1), 'afraid': (0, 0.2)})],
                        effects=dict(boredom=-0.3)),
    'groom': dict(bias=-1.2, emotions=dict(content=0.5, bored=0.8, frustrated=0.5, afraid=-2.0, excited=-1.0),
                  features=dict(groom_need=4.5), interest_tau=90,
                  clips=[('preen', 3), ('rouse_feathers', 2), ('scratch_belly', 2), ('fluff_shake', 1),
                         ('wing_stretch', 0.7), ('beak_wipe', 0.6)],
                  effects=dict(groom_need=-0.17)),
    'stretch': dict(bias=-3.0, features=dict(just_woke=5.0), interest_tau=10,
                    clips=[('wing_stretch', 2), ('yawn', 1.5), ('rouse_feathers', 1.5)]),
    'play': dict(bias=-0.8, emotions=dict(playful=2.5, happy=0.5), features=dict(music=1.0, cursor_gentle=1.5),
                 requires=dict(playful=0.2), interest_tau=30,
                 clips=[('playful_crouch', 2), ('happy_dance', 2), ('happy_dance', 4, {'music': (0.5, 1)}),
                        ('funny_shake', 1.5), ('hop', 1), ('tail_shake', 1), ('wing_flap', 0.8)],
                 effects=dict(boredom=-0.5, sleep=0.004)),
    'celebrate': dict(bias=-0.8, emotions=dict(happy=2.5, excited=0.8), features=dict(cursor_gentle=0.5),
                      requires=dict(happy=0.3), interest_tau=15,
                      clips=[('happy_bounce', 2), ('happy_full', 2, {'happy': (0.6, 1)}), ('tail_wag', 1.5),
                             ('fluff_shake', 1)],
                      effects=dict(boredom=-0.2)),
    'show_off': dict(bias=-1.0, emotions=dict(proud=3.0), requires=dict(proud=0.3, present=0.4), interest_tau=20,
                     clips=[('show_off_strut', 3), ('wing_display', 1.5), ('tail_fan', 1)]),
    'affection': dict(bias=-0.8, emotions=dict(affectionate=2.5),
                      features=dict(attention=0.8, petting=-2.0, pet_bad=-3.0, head_touch=2.5),
                      requires=dict(affectionate=0.3, present=0.4, attention=0.15), interest_tau=40,
                      clips=[('ask_head_scratch', 3, {'cursor_near': (0.25, 1)}),
                             ('love_head_bob', 0.6, {'bond': (0.6, 1), 'attention': (0.3, 1)}),
                             ('curious_tilt', 1)]),
    'approach_hand': dict(bias=-0.9, emotions=dict(excited=1.5, affectionate=1.5, happy=0.5),
                          # v3: the hand is already scratching (petting) or just hurt (pet_bad) -> stop approaching it
                          features=dict(hand_good=2.5, touch_need=1.0, social_need=0.5, petting=-5.0, pet_bad=-5.0,
                                        irritation=-5.0, head_touch=-6.0),     # v4: the hand is already there
                          requires=dict(hand_good=0.3),
                          priority=1, interest_tau=25,
                          clips=[('walk_cycle', 3, {'cursor_near': (0, 0.3)}), ('anticipate', 2, {'cursor_near': (0.3, 1)}),
                                 ('happy_bounce', 1.5, {'cursor_near': (0.3, 1), 'excited': (0.4, 1)}),
                                 ('ask_head_scratch', 2.5, {'cursor_near': (0.45, 1), 'touch_need': (0.3, 1)}),
                                 ('love_head_bob', 1, {'cursor_near': (0.3, 1), 'bond': (0.6, 1)}),
                                 # v4: a hand close by is first of all interesting
                                 ('curious_peek', 2, {'cursor_near': (0.3, 1), 'curious': (0.6, 1)}),
                                 ('curious_tilt', 1.5, {'cursor_near': (0.3, 1), 'curious': (0.6, 1)})]),
    'solicit_petting': dict(bias=-1.6, emotions=dict(affectionate=1.5, lonely=0.5),
                            features=dict(touch_need=3.5, present=0.5, unanswered=-3.0, night=-3.0, petting=-4.0,
                                          pet_bad=-3.0),
                            requires=dict(touch_need=0.5, present=0.3), interest_tau=40, request=True,
                            clips=[('ask_head_scratch', 3, {'cursor_near': (0.2, 1)}),
                                   ('walk_cycle', 2, {'cursor_near': (0, 0.2)}),
                                   ('love_head_bob', 1, {'bond': (0.6, 1)}), ('curious_tilt', 1)]),
    'avoid_hand': dict(bias=-0.4, emotions=dict(frustrated=1.0, angry=0.5, afraid=1.0),
                       features=dict(pet_bad=5.0, irritation=3.5, comfort=-3.0),
                       requires=dict(annoyed=0.3), priority=1, interest_tau=12,
                       clips=[('wary_lean_back', 2), ('sulk_turn_away', 1.5), ('wing_flick', 1),
                              ('warn_lunge', 1.5, {'angry': (0.6, 1)})]),     # v4: lunges = repeated clicking
    'enjoy_petting': dict(bias=0.0, features=dict(petting=6.0, head_touch=2.5), requires=dict(petting=0.25), priority=1,
                          interest_tau=600, clips=[('head_scratched', 1)],
                          effects=dict(social_need=-0.5, groom_need=-0.1)),
    'request_food': dict(bias=-1.2, emotions=dict(hungry=2.0),
                         features=dict(exp_food=1.0, present=1.0, unanswered=-3.0),
                         requires=dict(hungry=0.35, present=0.3), interest_tau=30, request=True,
                         clips=[('knock_screen', 3), ('anticipate', 1.5), ('walk_to_screen', 0.5)]),
    'anticipate': dict(bias=-1.0, emotions=dict(excited=2.0), features=dict(exp_food=1.5),
                       requires=dict(excited=0.3), interest_tau=20,
                       clips=[('anticipate', 3), ('wing_flutter', 1)]),
    'contact_call': dict(bias=-0.8, emotions=dict(lonely=3.0), features=dict(unanswered=-4.0, night=-3.0),
                         requires=dict(lonely=0.35), interest_tau=25,
                         request=True, clips=[('lonely_call', 3), ('squawk', 1)]),
    'chatter': dict(bias=-1.8, emotions=dict(happy=1.0, content=0.3), features=dict(present=1.0, talk=2.0),
                    requires=dict(present=0.4), interest_tau=20, clips=[('talk', 1)],
                    effects=dict(social_need=-0.05)),
    'wander': dict(bias=-1.3, emotions=dict(bored=0.8, curious=0.5), interest_tau=20,
                   clips=[('walk_cycle', 2), ('step_left', 1.5), ('step_right', 1.5), ('hop', 0.5)],
                   effects=dict(boredom=-0.2)),
    'exercise': dict(bias=-2.5, emotions=dict(playful=0.5, happy=0.3), features=dict(boredom=0.8),
                     urge=dict(rate_h=2.0, gain=2.5, discharge=0.6), interest_tau=10,
                     clips=[('wing_flap', 2), ('wing_flutter', 1), ('flap_takeoff', 0.5)],
                     effects=dict(boredom=-0.3, sleep=0.006)),
    'mope': dict(bias=-0.5, emotions=dict(sad=3.0), features=dict(hand_sad=2.0), requires=dict(sad=0.3), interest_tau=90,
                 clips=[('sad_idle', 3), ('wing_droop', 2), ('sulk_turn_away', 1, {'attention': (0.3, 1)})]),
    'bored_idle': dict(bias=-0.8, emotions=dict(bored=2.5), requires=dict(bored=0.3), interest_tau=40,
                       clips=[('bored_sigh', 2), ('yawn', 1), ('tail_bob', 1)]),
    'frustration': dict(bias=-0.8, emotions=dict(frustrated=3.0), requires=dict(frustrated=0.3), interest_tau=20,
                        clips=[('frustrated_pace', 2), ('beak_wipe', 1), ('wing_flick', 1), ('tail_flick', 1),
                               ('grumpy_grumble', 5, {'sleep_debt': (0.35, 1)})]),     # v5: over-tired grumbling
    'threaten': dict(bias=-0.5, emotions=dict(angry=3.0), features=dict(pet_bad=2.5, poke=1.0, irritation=-1.5),
                     requires=dict(angry=0.3), priority=2, interest_tau=12,
                     clips=[('angry_puff', 2, {'angry': (0.3, 0.7)}), ('warn_lunge', 2, {'angry': (0.6, 1)}),
                            ('angry_full', 2, {'angry': (0.7, 1)}),
                            ('grumpy_grumble', 3, {'sleepy': (0.35, 1)})]),
    'fear': dict(bias=-0.5, emotions=dict(afraid=3.0), requires=dict(afraid=0.3), priority=2, interest_tau=30,
                 clips=[('scared_sleek', 2), ('wary_lean_back', 1)]),
    'startle': dict(bias=0.0, emotions=dict(startled=6.0), requires=dict(startled=0.35), priority=3,
                    interest_tau=3, clips=[('startle_flinch', 3), ('shocked', 1, {'mood_neg': (0.1, 1)}),
                                           ('surprised', 1, {'mood_pos': (0.1, 1)})]),
    'doze': dict(bias=-0.8, emotions=dict(sleepy=2.5), features=dict(sleep_debt=1.0), requires=dict(sleepy=0.3),
                 interest_tau=120,
                 clips=[('sleepy', 3), ('rest_one_leg', 1), ('yawn', 1), ('beak_grind', 1)]),
    'sleep': dict(bias=-1.5, emotions=dict(sleepy=4.0), features=dict(night=3.0, sleep_debt=1.5),
                  requires=dict(sleepy=0.55),
                  interest_tau=36000, persist=2.0, clips=[('sleep', 1)]),
    'mischief': dict(bias=-0.8, emotions=dict(mischievous=3.0), requires=dict(mischievous=0.3), interest_tau=15,
                     clips=[('naughty', 2), ('funny_shake', 1)]),
    'greet': dict(bias=0.0, features=dict(reunion=6.0), requires=dict(reunion=0.3), priority=1, interest_tau=5,
                  clips=[('greet', 3), ('happy_full', 1), ('wing_flick', 0.5)], effects=dict(reunion=-30.0)),
}

# Behaviour selection stability (v4): a running behaviour keeps passing its 'requires' gate down to this fraction of
# the entry threshold (Schmitt-trigger hysteresis), and a running priority behaviour is not swapped out by the random
# choice at a clip end while its own motivation is within keep_margin of the best alternative. Without this, a
# trigger hovering at its threshold (petting between strokes) made the bird leave and re-enter within a second.
SELECTION = dict(stay_gate=0.4, keep_margin=0.5)

# Group bias offsets found by tools calibrate.py (simulated days vs TIME_BUDGET_TARGET). Added to every
# behaviour bias in the group.
GROUP_BIAS = dict(calm=-0.602, groom=-0.601, social=0.296, play=0.559, explore=0.02, negative=-0.446)

# Feeding sequences started by the right-click menu (the bird's reaction inside them is still emotional:
# beg / nibble loop counts and the aftermath come from the network). value = how much the offer excites
# (sunflower = fatty favourite, millet = everyday treat).
FEEDING = {
    'sunflower': dict(value=1.2, see='feed_sunflower_see', beg='feed_sunflower_beg', eat='feed_sunflower_eat', more=None,
                      beg_logit=('excited', 4.0, 'hunger', 2.0, -2.5), max_loops=4),
    'millet': dict(value=0.35, see='feed_millet_see', beg=None, eat='feed_millet_eat', more='feed_millet_nibble',
                   more_logit=('hunger', 3.0, 'happy', 2.0, -1.2), max_loops=5),
}

# Stochastic (Poisson) physiological events and expression outputs; rates per second.
POISSON = dict(sneeze=1 / 7200.0, blink_base=0.22, blink_sleepy=0.45, blink_afraid=-0.12, saccade_base=0.3)

# Behaviour groups used for reports / time-budget calibration.
GROUPS = {
    'calm': ('rest', 'look_around', 'watch_user', 'doze'),
    'groom': ('groom', 'stretch'),
    'social': ('affection', 'enjoy_petting', 'chatter', 'contact_call', 'greet', 'request_food', 'anticipate',
               'approach_hand', 'solicit_petting'),
    'play': ('play', 'celebrate', 'show_off', 'mischief', 'exercise'),
    'explore': ('investigate', 'wander'),
    'negative': ('mope', 'bored_idle', 'frustration', 'threaten', 'fear', 'startle', 'avoid_hand'),
    'sleep': ('sleep',),
    'feeding': ('feed',),
}

# Published reference points the calibration aims for (daytime, user around, kind owner).
TIME_BUDGET_TARGET = dict(calm=(0.40, 0.60), groom=(0.07, 0.15), explore=(0.03, 0.10), social=(0.05, 0.15),
                          play=(0.04, 0.12), negative=(0.0, 0.08))

REFERENCES = [
    'Yoo S-S, Gujar N, Hu P, Jolesz FA, Walker MP (2007) The human emotional brain without sleep - a prefrontal '
    'amygdala disconnect. Curr Biol 17:R877-R878. (sleep loss amplifies negative reactivity; used for SLEEP_DEBT)',
    'Companion-parrot husbandry guidance (PetMD; Merck Veterinary Manual; avian behaviour consultants): 10-12 h of '
    'dark, quiet sleep; birds kept up late become irritable, noisy and nippy. Practice guidance, not a controlled '
    'study.',
    'Mendl M, Burman OHP, Paul ES (2010) An integrative and functional framework for the study of animal emotion '
    'and mood. Proc R Soc B 277:2895-2904.',
    'Russell JA (1980) A circumplex model of affect. J Pers Soc Psychol 39:1161-1178.',
    'Panksepp J (1998) Affective Neuroscience; Panksepp J (2011) Cross-species affective neuroscience.',
    'Breazeal C (2003) Emotion and sociable humanoid robots. Int J Human-Computer Studies 59:119-155 (Kismet).',
    'Grand S, Cliff D, Malhotra A (1997) Creatures: artificial life autonomous software agents for home '
    'entertainment. Autonomous Agents (norn neural net + biochemistry).',
    'Becker-Asano C (2008) WASABI: affect simulation for agents with believable interactivity; Gebhard P (2005) '
    'ALMA - a layered model of affect.',
    'Lorenz K (1950) psycho-hydraulic model; Blumberg B (1996) Old Tricks, New Dogs: Ethology and Interactive '
    'Creatures (MIT PhD).',
    'Borbely AA (1982) A two process model of sleep regulation. Hum Neurobiol 1:195-204.',
    'van Zeeland YRA et al. (2023) Contrafreeloading indicating the behavioural need to forage in healthy and '
    'feather damaging grey parrots. Animals 13:2635 (preening 10 +- 6 % of daytime; morning/afternoon peaks).',
    'Rozek JC, Millam JR (2011) Preference and motivation for different diet forms in orange-winged Amazon '
    'parrots. Appl Anim Behav Sci (captive parrots off-perch ~6 % of the day).',
    'Cussen VA, Mench JA (2014) Personality predicts cognitive bias in captive psittacines. Anim Behav 89:123-130.',
    'Bertin A et al. (2018) Facial display and blushing: means of visual communication in blue-and-yellow '
    'macaws? PLoS ONE 13:e0201762.',
    'Schwing R et al. (2017) Positive emotional contagion in a New Zealand parrot. Curr Biol 27:R213-R214.',
    'Rescorla RA, Wagner AR (1972) A theory of Pavlovian conditioning; Thompson RF, Spencer WA (1966) '
    'Habituation; Amsel A (1958) frustration theory.',
    'Lafeber Pet Birds: Ask Lafeber - Hormonal triggers / Petting birds (limit petting to head and neck; tail, lower '
    'back, below the chest are hormonal hot spots); Lafeber: Pet bird and parrot behavior (stroke head/neck against '
    'the grain, rub cheeks in soft circles).',
    'PetMD: Small conure care sheet (pinned eyes, flared tail, lunging precede bites); Prego Dalliance Sanctuary: '
    'Understanding parrot body language (growling birds do not want to be touched; a series of clicks is a warning).',
    'Lafeber Vet: Reading bird body language; Parrot Fun Zone: Understand your bird\'s body language; '
    'Wikipedia: Sun parakeet (flock contact calls; quiet while feeding).',
    'Scherer KR (2001) Appraisal considered as a process of multilevel sequential checking (appraisal layer: what the '
    'hand is doing - novelty, pleasantness, provocation).',
    'Beer RD (1995) On the dynamics of small continuous-time recurrent neural networks; Husbands P et al. (1998) '
    'GasNets: neuromodulated time constants in evolved controllers (comfort -> faster decay of RAGE/FEAR).',
    'Kenny E, Birkhead TR, Green JP (2017) Allopreening in birds is associated with parental cooperation over offspring '
    'care and stable pair bonds across years. Behav Ecol 28:1142-1148 (gentle touch maintains the pair bond).',
    'Kiyokawa Y, Hennessy MB (2018) Comparative studies of social buffering. Neurosci Biobehav Rev 86:131-141 '
    '(affiliative partners mitigate stress responses; stronger with a close relationship -> comfort x bond).',
    'Friedman SG: Behavior Fundamentals / Straight Talk about Parrot Behavior (World Parrot Trust): food is the main '
    'positive reinforcer for companion parrots. Caveat (not modelled): food delivered right AFTER a lunge can '
    'reinforce lunging; here food only calms the current anger.',
]
