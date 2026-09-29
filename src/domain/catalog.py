from dataclasses import dataclass

PHASE_DAYS = 14
EXTRA_UNLOCK_STREAK = 3

Objective = tuple[str, tuple[str, ...]]
Stage = tuple[str, str, str, list[Objective], Objective]


@dataclass(frozen=True)
class CatalogImplementation:
    id: str
    title: str


@dataclass(frozen=True)
class CatalogCommitment:
    id: str
    objective: str
    unlock_streak: int
    implementations: tuple[CatalogImplementation, ...]
    recurrence: str
    times_per_week: int | None
    weekdays: tuple[int, ...]
    month_day: int | None


@dataclass(frozen=True)
class CatalogPhase:
    id: str
    name: str
    headline: str
    length_days: int
    commitments: tuple[CatalogCommitment, ...]


@dataclass(frozen=True)
class CatalogDirection:
    id: str
    name: str
    phases: tuple[CatalogPhase, ...]


@dataclass(frozen=True)
class CatalogIdentity:
    id: str
    name: str
    directions: tuple[CatalogDirection, ...]


def _recurrence(kind: str, index: int) -> tuple[str, int | None, tuple[int, ...], int | None]:
    if kind == "extra":
        return "weekly", None, (0,), None
    if index == 0:
        return "daily", None, (), None
    return "times_per_week", 3, (0, 2, 4), None


def _commitment(
    phase_id: str,
    kind: str,
    index: int,
    objective: str,
    titles: tuple[str, ...],
    unlock_streak: int,
) -> CatalogCommitment:
    commitment_id = f"{phase_id}-{kind}-{index}"
    recurrence, times_per_week, weekdays, month_day = _recurrence(kind, index)
    return CatalogCommitment(
        id=commitment_id,
        objective=objective,
        unlock_streak=unlock_streak,
        implementations=tuple(
            CatalogImplementation(id=f"{commitment_id}-{item}", title=title)
            for item, title in enumerate(titles)
        ),
        recurrence=recurrence,
        times_per_week=times_per_week,
        weekdays=weekdays,
        month_day=month_day,
    )


def _phase(
    direction_id: str,
    slug: str,
    name: str,
    headline: str,
    bases: list[Objective],
    extra: Objective,
) -> CatalogPhase:
    phase_id = f"{direction_id}-{slug}"
    commitments = [
        _commitment(phase_id, "base", index, objective, titles, 0)
        for index, (objective, titles) in enumerate(bases)
    ]
    commitments.append(
        _commitment(phase_id, "extra", 0, extra[0], extra[1], EXTRA_UNLOCK_STREAK)
    )
    return CatalogPhase(
        id=phase_id,
        name=name,
        headline=headline,
        length_days=PHASE_DAYS,
        commitments=tuple(commitments),
    )


def _direction(slug: str, name: str, stages: list[Stage]) -> CatalogDirection:
    return CatalogDirection(
        id=slug,
        name=name,
        phases=tuple(_phase(slug, *stage) for stage in stages),
    )


def _identity(slug: str, name: str, directions: list[CatalogDirection]) -> CatalogIdentity:
    return CatalogIdentity(id=slug, name=name, directions=tuple(directions))


def _pair(objective: str, first: str, second: str) -> Objective:
    return (objective, (first, second))


_DISCIPLINED = _identity(
    "disciplined",
    "Disciplined",
    [
        _direction(
            "master-deep-work",
            "Master deep work",
            [
                (
                    "foundation",
                    "Foundation",
                    "Keep One Promise",
                    [
                        _pair(
                            "Work without interruption",
                            "15 minutes of uninterrupted work",
                            "One task, with everything else closed",
                        ),
                        _pair(
                            "Begin before you feel ready",
                            "Open the work and stay with it for 15 minutes",
                            "Start with the smallest hard piece",
                        ),
                    ],
                    _pair(
                        "Protect the start of the work",
                        "No phone during the first hour of work",
                        "Leave your phone in another room for the first hour",
                    ),
                ),
                (
                    "consistency",
                    "Consistency",
                    "Consistency",
                    [
                        _pair(
                            "Return to the same work",
                            "Sit down at the same time and work for 25 minutes",
                            "Reopen yesterday's task before anything new",
                        ),
                        _pair(
                            "Finish a small piece",
                            "Close one loop before you leave the desk",
                            "Ship one small piece of the work",
                        ),
                    ],
                    _pair(
                        "Guard the block",
                        "Decline one interruption during the work block",
                        "Silence notifications for the work block",
                    ),
                ),
                (
                    "focus",
                    "Focus",
                    "Focus",
                    [
                        _pair(
                            "Stay on one problem",
                            "Work on a single problem for 40 minutes",
                            "Write the problem down and stay with it",
                        ),
                        _pair(
                            "Cut the noise",
                            "Close every tab that is not the work",
                            "Put the phone out of reach before you start",
                        ),
                    ],
                    _pair(
                        "Deepen the block",
                        "Add 15 quiet minutes to the work block",
                        "Take one harder pass after the first block",
                    ),
                ),
                (
                    "self-control",
                    "Self-Control",
                    "Self-Control",
                    [
                        _pair(
                            "Choose the work over the pull",
                            "When you reach for the phone, return to the work",
                            "Wait ten minutes before you switch tasks",
                        ),
                        _pair(
                            "End the day on purpose",
                            "Stop at the time you chose",
                            "Write tomorrow's first task before you close",
                        ),
                    ],
                    _pair(
                        "Hold the standard",
                        "Do the work block even if it starts late",
                        "Finish the block before any reward",
                    ),
                ),
            ],
        ),
        _direction(
            "build-a-morning-routine",
            "Build a morning routine",
            [
                (
                    "wake",
                    "Wake",
                    "Get up",
                    [
                        _pair(
                            "Get up when you said you would",
                            "Get out of bed at your chosen time",
                            "Put your feet on the floor before you check the phone",
                        ),
                        _pair(
                            "Start before the day starts you",
                            "Leave the bed and open the curtains",
                            "Drink a glass of water before anything else",
                        ),
                    ],
                    _pair(
                        "Keep the first minutes quiet",
                        "No phone for the first 15 minutes",
                        "Leave the phone in another room overnight",
                    ),
                ),
                (
                    "order",
                    "Order",
                    "Order the room",
                    [
                        _pair(
                            "Leave one thing in order",
                            "Make your bed before you leave the room",
                            "Clear the surface you will use today",
                        ),
                        _pair(
                            "Prepare the next start",
                            "Set out what you need for the morning",
                            "Choose tomorrow's first action tonight",
                        ),
                    ],
                    _pair(
                        "Hold the sequence",
                        "Do the same three steps in the same order",
                        "Repeat the routine even if you woke up late",
                    ),
                ),
                (
                    "stillness",
                    "Stillness",
                    "Be still",
                    [
                        _pair(
                            "Sit before you rush",
                            "Sit quietly for five minutes",
                            "Write one page before you open a screen",
                        ),
                        _pair(
                            "Name the day",
                            "Write the one thing that matters today",
                            "Read the promise you made last night",
                        ),
                    ],
                    _pair(
                        "Protect the quiet",
                        "Keep the first half hour free of messages",
                        "Do not open email until the routine is done",
                    ),
                ),
                (
                    "follow-through",
                    "Follow-through",
                    "Leave on time",
                    [
                        _pair(
                            "Finish the routine",
                            "Complete the routine before you sit down to work",
                            "Do not skip the last step",
                        ),
                        _pair(
                            "Leave the morning clean",
                            "Walk out with the bed made and the phone still down",
                            "Start the work only after the routine is done",
                        ),
                    ],
                    _pair(
                        "Keep it on a hard morning",
                        "Do a shorter version rather than skip it",
                        "Start the routine even if you only have ten minutes",
                    ),
                ),
            ],
        ),
        _direction(
            "break-a-bad-habit",
            "Break a bad habit",
            [
                (
                    "notice",
                    "Notice",
                    "Catch it",
                    [
                        _pair(
                            "See the habit before you follow it",
                            "Name the urge when it shows up",
                            "Write down the time you wanted the habit",
                        ),
                        _pair(
                            "Pause at the trigger",
                            "Wait two minutes when the cue appears",
                            "Put the cue out of reach",
                        ),
                    ],
                    _pair(
                        "Interrupt once",
                        "Leave the room when the urge hits",
                        "Do ten slow breaths instead of the habit",
                    ),
                ),
                (
                    "replace",
                    "Replace",
                    "Swap it",
                    [
                        _pair(
                            "Do something else at the cue",
                            "Take a short walk when the urge hits",
                            "Drink water and wait it out",
                        ),
                        _pair(
                            "Make the habit harder",
                            "Add one step of friction before the habit",
                            "Remove the easiest version of the habit from reach",
                        ),
                    ],
                    _pair(
                        "Hold the line later",
                        "Refuse it once more in the evening",
                        "End the day without returning to it",
                    ),
                ),
                (
                    "distance",
                    "Distance",
                    "Create distance",
                    [
                        _pair(
                            "Stay away from the setup",
                            "Avoid the place where the habit usually happens",
                            "Change the route that leads you into it",
                        ),
                        _pair(
                            "Shrink the window",
                            "Delay the habit until a time you chose",
                            "Cut the usual amount in half",
                        ),
                    ],
                    _pair(
                        "Tell the truth about it",
                        "Write whether you followed it today",
                        "Note the cue that almost won",
                    ),
                ),
                (
                    "free",
                    "Free",
                    "Stay free",
                    [
                        _pair(
                            "Go through the cue without the habit",
                            "Meet the usual cue and do not follow it",
                            "Keep the replacement when the day gets hard",
                        ),
                        _pair(
                            "Close the day clean",
                            "End the day without the habit",
                            "Put the tools of the habit away for tomorrow",
                        ),
                    ],
                    _pair(
                        "Recover without restarting",
                        "If you slip, return to the replacement the same day",
                        "Do not turn one slip into the rest of the day",
                    ),
                ),
            ],
        ),
        _direction(
            "build-willpower",
            "Build willpower",
            [
                (
                    "one-hard-thing",
                    "One hard thing",
                    "Do one hard thing",
                    [
                        _pair(
                            "Do one thing you want to avoid",
                            "Do the task you have been postponing for 10 minutes",
                            "Start the hard thing before the easy thing",
                        ),
                        _pair(
                            "Stay a little longer",
                            "Continue for five minutes after you want to stop",
                            "Finish the set you said you would",
                        ),
                    ],
                    _pair(
                        "Choose discomfort once more",
                        "Take the harder option once today",
                        "Do it before you negotiate with yourself",
                    ),
                ),
                (
                    "delay",
                    "Delay",
                    "Wait",
                    [
                        _pair(
                            "Wait before the reward",
                            "Delay a comfort by 20 minutes",
                            "Finish the task before you check the phone",
                        ),
                        _pair(
                            "Keep a small promise",
                            "Do the thing you told yourself this morning",
                            "Do not move the task to tomorrow",
                        ),
                    ],
                    _pair(
                        "Hold two standards",
                        "Keep the delay even after a long day",
                        "Do the hard thing and the small promise",
                    ),
                ),
                (
                    "standard",
                    "Standard",
                    "Keep the standard",
                    [
                        _pair(
                            "Do it at the standard you set",
                            "Complete the hard thing to the line you drew",
                            "Do not accept a sloppy version",
                        ),
                        _pair(
                            "Practice the no",
                            "Say no to one distraction",
                            "Leave one pleasure for later",
                        ),
                    ],
                    _pair(
                        "Raise it slightly",
                        "Add five minutes to the hard thing",
                        "Do one extra repetition of the standard",
                    ),
                ),
                (
                    "command",
                    "Command",
                    "Command yourself",
                    [
                        _pair(
                            "Act when you decide",
                            "Start within one minute of deciding",
                            "Do the next right action without a warm-up ritual",
                        ),
                        _pair(
                            "Finish what you opened",
                            "Close the task you started",
                            "Do not leave the hard thing half done",
                        ),
                    ],
                    _pair(
                        "Keep command at night",
                        "Do the evening version of the hard thing",
                        "Go to bed at the time you set",
                    ),
                ),
            ],
        ),
        _direction(
            "follow-through-daily",
            "Follow through daily",
            [
                (
                    "promise",
                    "Promise",
                    "Keep today's promise",
                    [
                        _pair(
                            "Do the thing you named",
                            "Complete the one promise you wrote down",
                            "Do it before noon",
                        ),
                        _pair(
                            "Make the promise visible",
                            "Write the promise where you will see it",
                            "Read it once before you start the day",
                        ),
                    ],
                    _pair(
                        "Do it even if it is small",
                        "Keep the promise in a shorter form",
                        "Do not replace the promise with a different task",
                    ),
                ),
                (
                    "same-hour",
                    "Same hour",
                    "Show up at the hour",
                    [
                        _pair(
                            "Show up at the chosen hour",
                            "Start at the time you set",
                            "Be in the place you chose when the hour arrives",
                        ),
                        _pair(
                            "Stay for the whole block",
                            "Remain until the block is over",
                            "Do not leave early",
                        ),
                    ],
                    _pair(
                        "Protect the hour",
                        "Decline one thing that would move the hour",
                        "Set a reminder and obey it",
                    ),
                ),
                (
                    "close",
                    "Close",
                    "Close the loop",
                    [
                        _pair(
                            "Finish what you opened",
                            "Close one open loop",
                            "Send the thing you have been holding",
                        ),
                        _pair(
                            "Record that you did it",
                            "Mark the promise done when it is done",
                            "Write one line about what you finished",
                        ),
                    ],
                    _pair(
                        "Name tomorrow",
                        "Write tomorrow's promise before the day ends",
                        "Leave the first step ready",
                    ),
                ),
                (
                    "again",
                    "Again",
                    "Do it again",
                    [
                        _pair(
                            "Repeat the promise",
                            "Keep the same promise for another day",
                            "Do it without renegotiating",
                        ),
                        _pair(
                            "Do not miss twice",
                            "If yesterday slipped, do it today",
                            "Return the same day you notice the miss",
                        ),
                    ],
                    _pair(
                        "Make it ordinary",
                        "Do the promise as part of the day, not as a special effort",
                        "Keep it on a day when you do not feel like it",
                    ),
                ),
            ],
        ),
    ],
)

_HEALTHY = _identity(
    "healthy",
    "Healthy",
    [
        _direction(
            "move-daily",
            "Move daily",
            [
                (
                    "movement",
                    "Movement",
                    "Movement",
                    [
                        _pair(
                            "Move your body",
                            "Walk for 20 minutes",
                            "Ride easy for 20 minutes",
                        ),
                        _pair(
                            "Leave the chair",
                            "Take a 15-minute walk outside",
                            "Move through a short home circuit",
                        ),
                    ],
                    _pair(
                        "Move once more",
                        "Take a second 10-minute walk",
                        "Stretch for 10 minutes after the main walk",
                    ),
                ),
                (
                    "nutrition",
                    "Nutrition",
                    "Nutrition",
                    [
                        _pair(
                            "Eat one honest meal",
                            "Build one meal around protein and plants",
                            "Cook a simple meal instead of skipping it",
                        ),
                        _pair(
                            "Drink water with the day",
                            "Finish a full bottle of water before lunch",
                            "Drink a glass of water before each meal",
                        ),
                    ],
                    _pair(
                        "Close the kitchen on purpose",
                        "Stop eating at the time you set",
                        "Put the snacks away after dinner",
                    ),
                ),
                (
                    "strength",
                    "Strength",
                    "Strength",
                    [
                        _pair(
                            "Load your muscles",
                            "Do a 20-minute strength session",
                            "Carry something heavy on your walk",
                        ),
                        _pair(
                            "Use your body",
                            "Complete two rounds of squats, pushes, and hinges",
                            "Hold a plank and then walk for 10 minutes",
                        ),
                    ],
                    _pair(
                        "Add a little load",
                        "Do one more set than yesterday",
                        "Slow the lowering on each rep",
                    ),
                ),
                (
                    "endurance",
                    "Endurance",
                    "Endurance",
                    [
                        _pair(
                            "Stay moving longer",
                            "Move continuously for 30 minutes",
                            "Walk farther than your usual loop",
                        ),
                        _pair(
                            "Keep an easy pace",
                            "Go long enough that you could still talk",
                            "Finish the session even if you slow down",
                        ),
                    ],
                    _pair(
                        "Recover so you can go again",
                        "Walk slowly for five minutes at the end",
                        "Go to bed at the time that lets you move tomorrow",
                    ),
                ),
            ],
        ),
        _direction(
            "improve-my-sleep",
            "Improve my sleep",
            [
                (
                    "wind-down",
                    "Wind-down",
                    "Wind down",
                    [
                        _pair(
                            "Dim the evening",
                            "Lower the lights an hour before bed",
                            "Stop the bright screen 30 minutes before bed",
                        ),
                        _pair(
                            "Repeat a short close",
                            "Do the same quiet routine before bed",
                            "Read a few pages instead of scrolling",
                        ),
                    ],
                    _pair(
                        "Leave the phone out",
                        "Charge the phone outside the bedroom",
                        "Do not check it after you lie down",
                    ),
                ),
                (
                    "hour",
                    "Hour",
                    "Keep the hour",
                    [
                        _pair(
                            "Go to bed at the hour",
                            "Be in bed at the time you chose",
                            "Start winding down early enough to make the hour",
                        ),
                        _pair(
                            "Get up at the hour",
                            "Get up at the same time",
                            "Open the curtains when the alarm goes",
                        ),
                    ],
                    _pair(
                        "Protect the last hour",
                        "No work in the last hour of the day",
                        "No hard conversation in the last hour",
                    ),
                ),
                (
                    "body",
                    "Body",
                    "Let the body down",
                    [
                        _pair(
                            "Drop the day from your body",
                            "Stretch slowly for ten minutes",
                            "Take a warm shower and then sit still",
                        ),
                        _pair(
                            "Keep caffeine in its place",
                            "Have no caffeine after the hour you set",
                            "Swap the late cup for water",
                        ),
                    ],
                    _pair(
                        "Make the room ready",
                        "Cool and darken the room before bed",
                        "Set out tomorrow so the night stays quiet",
                    ),
                ),
                (
                    "keep",
                    "Keep",
                    "Keep the night",
                    [
                        _pair(
                            "Treat the night as a promise",
                            "Keep the bedtime even after a messy day",
                            "Return to the routine if the evening ran long",
                        ),
                        _pair(
                            "Wake without negotiating",
                            "Get up without a second sleep",
                            "Leave the bed when you wake",
                        ),
                    ],
                    _pair(
                        "Guard the morning after",
                        "Get daylight soon after waking",
                        "Do not repay a short night with an endless morning",
                    ),
                ),
            ],
        ),
        _direction(
            "eat-with-intention",
            "Eat with intention",
            [
                (
                    "notice-food",
                    "Notice",
                    "Notice the meal",
                    [
                        _pair(
                            "Eat one meal without a screen",
                            "Sit down for one meal with the phone away",
                            "Eat at a table instead of on the move",
                        ),
                        _pair(
                            "Name what you are eating",
                            "Say what is on the plate before you start",
                            "Serve the portion before you begin",
                        ),
                    ],
                    _pair(
                        "Stop when you meant to",
                        "Pause halfway through the meal",
                        "Leave the last bites if you are no longer hungry",
                    ),
                ),
                (
                    "build-meal",
                    "Build",
                    "Build the meal",
                    [
                        _pair(
                            "Include protein and plants",
                            "Add a protein and a plant to one meal",
                            "Cook a simple plate instead of grazing",
                        ),
                        _pair(
                            "Decide before you are hungry",
                            "Choose the next meal before the hunger hits",
                            "Shop or set out what that meal needs",
                        ),
                    ],
                    _pair(
                        "Keep one boundary",
                        "Skip the extra snack you did not plan",
                        "Drink water before you go back for more",
                    ),
                ),
                (
                    "rhythm",
                    "Rhythm",
                    "Keep a rhythm",
                    [
                        _pair(
                            "Eat at roughly the same times",
                            "Have your meals inside the window you chose",
                            "Do not skip the meal and then overeat later",
                        ),
                        _pair(
                            "Prepare one thing ahead",
                            "Make one part of tomorrow's meal tonight",
                            "Pack the meal you would otherwise skip",
                        ),
                    ],
                    _pair(
                        "Close the kitchen",
                        "Finish eating by the hour you set",
                        "Brush your teeth when the kitchen closes",
                    ),
                ),
                (
                    "enough",
                    "Enough",
                    "Eat enough",
                    [
                        _pair(
                            "Eat to support the day",
                            "Do not under-eat the meal that carries your work",
                            "Include a real lunch",
                        ),
                        _pair(
                            "Keep the intention on a social day",
                            "Decide what you will eat before you arrive",
                            "Eat slowly enough to notice you are done",
                        ),
                    ],
                    _pair(
                        "Tell the truth",
                        "Write what you ate without judging the page",
                        "Note the meal that did not match the intention",
                    ),
                ),
            ],
        ),
        _direction(
            "build-strength",
            "Build strength",
            [
                (
                    "practice",
                    "Practice",
                    "Practice strength",
                    [
                        _pair(
                            "Train your body",
                            "Complete a 20-minute strength practice",
                            "Do squats, pushes, and hinges for three rounds",
                        ),
                        _pair(
                            "Learn the movement",
                            "Practice one lift slowly",
                            "Film or watch one set and fix one thing",
                        ),
                    ],
                    _pair(
                        "Warm up properly",
                        "Spend five minutes preparing the joints you will load",
                        "Do an easy set before the work sets",
                    ),
                ),
                (
                    "load",
                    "Load",
                    "Add load",
                    [
                        _pair(
                            "Make it heavier or harder",
                            "Add a little load to one movement",
                            "Slow the hard part of the rep",
                        ),
                        _pair(
                            "Keep the form",
                            "Stop the set when the form breaks",
                            "Do fewer reps rather than ugly ones",
                        ),
                    ],
                    _pair(
                        "Write it down",
                        "Record the sets you did",
                        "Note what you will add next time",
                    ),
                ),
                (
                    "repeat",
                    "Repeat",
                    "Repeat the session",
                    [
                        _pair(
                            "Train again",
                            "Do the same session you did last time",
                            "Show up even if the load stays the same",
                        ),
                        _pair(
                            "Recover between",
                            "Walk for 15 minutes on the day between sessions",
                            "Sleep at the hour that lets you train",
                        ),
                    ],
                    _pair(
                        "Eat for the work",
                        "Have a protein-rich meal on the training day",
                        "Do not train on an empty, chaotic day without food",
                    ),
                ),
                (
                    "own",
                    "Own",
                    "Own the strength",
                    [
                        _pair(
                            "Train without drama",
                            "Start the session at the time you set",
                            "Finish the session you wrote down",
                        ),
                        _pair(
                            "Keep a joint honest",
                            "Move a stiff joint through its range",
                            "Stop if pain is sharp, and do the rest",
                        ),
                    ],
                    _pair(
                        "Leave stronger",
                        "Add one rep to a set you own",
                        "Carry the last set with full control",
                    ),
                ),
            ],
        ),
        _direction(
            "build-a-workout-habit",
            "Build a workout habit",
            [
                (
                    "show",
                    "Show",
                    "Show up to train",
                    [
                        _pair(
                            "Start the workout",
                            "Begin a 20-minute workout",
                            "Put on your training clothes and start",
                        ),
                        _pair(
                            "Make it easy to begin",
                            "Lay out the workout before you need it",
                            "Train at the same time",
                        ),
                    ],
                    _pair(
                        "Finish what you start",
                        "Stay until the 20 minutes are done",
                        "Do the cooldown you planned",
                    ),
                ),
                (
                    "place",
                    "Place",
                    "Keep a place",
                    [
                        _pair(
                            "Train in the place you chose",
                            "Go to the same spot to train",
                            "Clear a corner and use it",
                        ),
                        _pair(
                            "Use a simple session",
                            "Follow a written 20-minute session",
                            "Repeat a session you already know",
                        ),
                    ],
                    _pair(
                        "Do not renegotiate",
                        "Start within five minutes of the planned time",
                        "Train even if you shorten it",
                    ),
                ),
                (
                    "rhythm-train",
                    "Rhythm",
                    "Train on rhythm",
                    [
                        _pair(
                            "Hit the sessions you named",
                            "Complete today's planned session",
                            "Train on the day you put on the calendar",
                        ),
                        _pair(
                            "Recover on purpose",
                            "Walk or stretch on the off day",
                            "Go to bed so the next session is possible",
                        ),
                    ],
                    _pair(
                        "Prepare the next one",
                        "Set out clothes for the next session",
                        "Write the next session before this day ends",
                    ),
                ),
                (
                    "identity-train",
                    "Identity",
                    "Be someone who trains",
                    [
                        _pair(
                            "Train without waiting to feel ready",
                            "Start the workout before you debate it",
                            "Do the first ten minutes no matter what",
                        ),
                        _pair(
                            "Keep the appointment",
                            "Treat the workout like a meeting you do not cancel",
                            "Tell someone you are training today, then do it",
                        ),
                    ],
                    _pair(
                        "Return quickly",
                        "If you miss a session, train the next day",
                        "Do a short session rather than a perfect one",
                    ),
                ),
            ],
        ),
    ],
)


def _simple_direction(
    slug: str,
    name: str,
    stages: list[tuple[str, str, list[tuple[str, str, str]], tuple[str, str, str]]],
) -> CatalogDirection:
    built: list[Stage] = []
    for phase_slug, phase_name, bases, extra in stages:
        built.append(
            (
                phase_slug,
                phase_name,
                phase_name,
                [_pair(item[0], item[1], item[2]) for item in bases],
                _pair(extra[0], extra[1], extra[2]),
            )
        )
    return _direction(slug, name, built)


_FINANCIALLY_INDEPENDENT = _identity(
    "financially-independent",
    "Financially Independent",
    [
        _simple_direction(
            "save-money",
            "Save money",
            [
                ("see", "See the money", [("Know what left the account", "Write down what you spent today", "Check the balance before you buy")], ("Move money aside", "Transfer a set amount to savings", "Set the transfer before you spend")),
                ("cut", "Cut one leak", [("Remove one unnecessary cost", "Cancel or skip one thing you do not need", "Wait a day before a nonessential buy")], ("Name the leak", "Write the expense you will not repeat", "Compare it with what you are saving for")),
                ("automate", "Automate", [("Make the save happen first", "Move savings as soon as money arrives", "Lower the spending account, not the save")], ("Leave it there", "Do not move the savings back", "Give the savings account a name")),
                ("keep-saving", "Keep saving", [("Save on an ordinary day", "Transfer today's amount", "Save a smaller amount rather than zero")], ("Look at the number", "Check the savings once", "Write how many days you have saved")),
            ],
        ),
        _simple_direction(
            "build-an-emergency-fund",
            "Build an emergency fund",
            [
                ("name-fund", "Name the fund", [("Give the fund a home", "Open or choose the account for the fund", "Name the account so it is not spending money")], ("Set the first number", "Write the amount you are building toward", "Write today's starting balance")),
                ("feed", "Feed it", [("Add to the fund", "Transfer today's contribution", "Move a windfall into the fund")], ("Keep it separate", "Do not spend from the fund", "Remove the card if it is too easy to use")),
                ("protect", "Protect it", [("Leave the fund alone", "Pay today's expense from the spending account", "Write why the fund is not for this")], ("Add a little more", "Round a purchase into the fund", "Transfer the amount you did not spend")),
                ("stand", "Let it stand", [("Make today's deposit", "Add to the fund before you spend", "Deposit even a small amount")], ("Review the gap", "Write what is left to reach the number", "Note one expense that could have hit the fund")),
            ],
        ),
        _simple_direction(
            "increase-my-income",
            "Increase my income",
            [
                ("offer", "Make an offer", [("Do one thing that can be paid", "Send one message that could lead to work", "Finish a piece someone could buy")], ("Name the price", "Write what the work is worth", "Ask for the number instead of hinting")),
                ("skill", "Sell the skill", [("Practice the skill you sell", "Spend 30 minutes on the paid skill", "Improve one sample of the work")], ("Show the work", "Publish or send one example", "Ask one person to look at it")),
                ("ask", "Ask", [("Make the ask", "Send the proposal or the request", "Follow up on one unanswered ask")], ("Widen the chance", "Talk to one new person about the work", "Apply or pitch once")),
                ("collect", "Collect", [("Finish and get paid", "Complete the piece you promised", "Invoice or request the payment")], ("Raise the value", "Improve one offer before you send it again", "Write what you will charge next time")),
            ],
        ),
        _simple_direction(
            "start-a-business",
            "Start a business",
            [
                ("customer", "Find a customer", [("Talk to one person", "Have one conversation with someone who has the problem", "Write what they actually said")], ("Offer a small version", "Describe the smallest thing you could sell", "Send that offer to one person")),
                ("build", "Build", [("Make the thing smaller", "Work for 45 minutes on the offer", "Ship a rough version to one person")], ("Charge something", "Ask to be paid for the small version", "Write the price on the offer")),
                ("repeat-sale", "Repeat", [("Do the work again", "Deliver for the next person", "Improve one step that was clumsy")], ("Ask for the next", "Ask a happy person for an introduction", "Invite one more customer")),
                ("run", "Run it", [("Show up to the business", "Spend a focused block on the business", "Do the task that makes money before the rest")], ("Keep the books honest", "Write what came in and what went out", "Separate the business money from the rest")),
            ],
        ),
        _simple_direction(
            "pay-off-debt",
            "Pay off debt",
            [
                ("list", "List it", [("See the debt", "Write each balance you owe", "Write the one you will pay first")], ("Stop the bleed", "Do not add to that debt today", "Leave the card at home")),
                ("pay", "Pay", [("Pay more than the minimum", "Send today's extra payment", "Round the payment up")], ("Find the extra", "Move one unnecessary spend into the payment", "Sell or skip one thing and pay it in")),
                ("hold", "Hold the line", [("Make the payment on time", "Pay before the due date", "Schedule the payment so it cannot slip")], ("Refuse a new balance", "Do not open a new way to owe", "Wait a day before any purchase on credit")),
                ("close-debt", "Close it", [("Hit the target debt", "Pay toward the one you are closing", "Write the new balance")], ("Keep going", "Point the next payment at the following debt", "Do not pause because one bill is smaller")),
            ],
        ),
        _simple_direction(
            "invest-consistently",
            "Invest consistently",
            [
                ("setup", "Set it up", [("Make the contribution possible", "Confirm the account you invest from", "Write the amount you will invest each time")], ("Learn the vehicle", "Read one page about what you are buying", "Write why you will not touch it")),
                ("contribute", "Contribute", [("Put the money in", "Make today's contribution", "Automate the contribution if it is not already")], ("Leave it invested", "Do not move the investment because of one headline", "Close the app after you contribute")),
                ("ignore-noise", "Ignore the noise", [("Do the boring thing", "Contribute without checking the price first", "Stick to the amount you wrote")], ("Stay with the plan", "Do not sell because of a feeling", "Reread the reason you invest")),
                ("continue", "Continue", [("Invest again", "Make the contribution on schedule", "Invest a smaller amount rather than skip")], ("Review once", "Look at the plan, not the day's price", "Write whether you stayed with it")),
            ],
        ),
    ],
)

_CONFIDENT = _identity(
    "confident",
    "Confident",
    [
        _simple_direction(
            "speak-up",
            "Speak up",
            [
                ("voice", "Use your voice", [("Say the thing", "Speak once in the room", "Send the message you have been editing")], ("Say it cleaner", "State the point in one sentence", "Do not apologize for the point")),
                ("again-speak", "Say it again", [("Repeat the honesty", "Speak up a second time today", "Disagree once without softening it away")], ("Stay after", "Do not take it back", "Let the silence sit")),
                ("room", "Enter the room", [("Be present", "Arrive and take a place you can be seen", "Introduce yourself to one person")], ("Offer a view", "Give one opinion when you are asked", "Answer the question directly")),
                ("keep-voice", "Keep the voice", [("Speak on an ordinary day", "Say one true thing without a big occasion", "Post or send the work in your own words")], ("Hold eye contact", "Finish the sentence while looking at the person", "Do not look away to shrink the point")),
            ],
        ),
        _simple_direction(
            "hold-the-room",
            "Hold the room",
            [
                ("stand", "Stand in it", [("Take your place", "Stand or sit as if you belong there", "Uncross and settle before you speak")], ("Open", "Start the conversation instead of waiting", "Greet someone first")),
                ("pace", "Keep a pace", [("Speak slower", "Finish one thought before the next", "Pause instead of filling the gap")], ("Stay", "Remain in the conversation when it gets quiet", "Ask one question and listen")),
                ("boundary", "Hold a boundary", [("Do not shrink the ask", "Make the request at full size", "Repeat it once if it is brushed aside")], ("Leave cleanly", "End the conversation when it is done", "Do not linger to be liked")),
                ("return-room", "Return", [("Go back in", "Enter the next room the same way", "Speak in a meeting you could have skipped")], ("Keep your face", "Let a reaction pass without explaining yourself", "Stay kind and do not fold")),
            ],
        ),
        _simple_direction(
            "do-the-hard-thing",
            "Do the hard thing",
            [
                ("name-hard", "Name it", [("Pick the hard thing", "Write the thing you are avoiding", "Do the first five minutes of it")], ("Tell someone", "Say what you are going to do", "Put it on the calendar")),
                ("do-hard", "Do it", [("Complete a real piece", "Work on the hard thing for 25 minutes", "Send the hard message")], ("Stay through the discomfort", "Continue after the first urge to stop", "Do the part you like least")),
                ("public", "Let it be seen", [("Show the attempt", "Share a draft or a result", "Ask for the meeting")], ("Take the answer", "Read the reply without hiding", "Respond once, clearly")),
                ("again-hard", "Do another", [("Choose the next hard thing", "Write the next one and start it", "Do not replace it with a comfortable task")], ("Keep your nerve", "Do it before you feel confident", "Start even with a rough first line")),
            ],
        ),
        _simple_direction(
            "stop-seeking-approval",
            "Stop seeking approval",
            [
                ("decide", "Decide", [("Choose without a poll", "Make one decision without asking first", "Write the choice and act on it")], ("Leave it made", "Do not reopen the decision for reassurance", "Tell one person after, not before")),
                ("post", "Let it stand", [("Publish without over-editing", "Send the work after one pass", "Do not add a disclaimer that shrinks it")], ("Stop checking", "Do not refresh for a reaction", "Put the phone down after you send it")),
                ("self", "Use your standard", [("Judge it yourself", "Write whether it met your standard", "Change one thing for you, not for the crowd")], ("Decline a performance", "Skip one thing you would only do to be seen", "Say no to an invitation that is only for approval")),
                ("quiet-confidence", "Stay quiet", [("Do the work unseen", "Finish something nobody asked to see", "Do not announce it")], ("Receive praise cleanly", "Say thank you and do not deflect", "Do not fish for a second compliment")),
            ],
        ),
    ],
)

_FOCUSED = _identity(
    "focused",
    "Focused",
    [
        _simple_direction(
            "protect-your-morning",
            "Protect your morning",
            [
                ("first-hour", "First hour", [("Give the morning to one thing", "Spend the first work hour on the important task", "Do not open the inbox first")], ("Start on time", "Begin at the hour you set", "Sit down before you wander")),
                ("gate", "Gate", [("Keep the gate", "Let no meeting into the first hour", "Tell one person you are unavailable")], ("One tab", "Keep a single piece of work open", "Close what is not the morning task")),
                ("depth", "Depth", [("Stay in it", "Work for a full quiet block", "Return immediately when you drift")], ("Capture, don't chase", "Write interruptions on a list and stay", "Answer them after the block")),
                ("hand-off", "Hand off the morning", [("End the block cleanly", "Write where you stopped", "Leave the next step obvious")], ("Protect it tomorrow", "Block the same hour for tomorrow", "Do not give the hour away tonight")),
            ],
        ),
        _simple_direction(
            "single-task",
            "Single-task",
            [
                ("one", "One thing", [("Do one thing at a time", "Finish a block on a single task", "Put the phone out of sight")], ("Name it", "Write the task before you start", "Do not add a second task to the block")),
                ("resist", "Resist the switch", [("Stay when you want to switch", "Return to the task when you notice a tab", "Finish a small unit before you move")], ("Clear the desk", "Remove the other work from view", "Close the chat for the block")),
                ("complete-one", "Complete one", [("Ship the one thing", "Reach a stopping point you defined", "Do not half-finish and hop")], ("Note the pull", "Write what tried to steal the block", "Deal with it later")),
                ("repeat-single", "Repeat", [("Single-task again", "Run another block the same way", "Choose the task before you sit down")], ("Make it normal", "Do an ordinary task with full attention", "Do not multitask the easy thing either")),
            ],
        ),
        _simple_direction(
            "finish-what-you-start",
            "Finish what you start",
            [
                ("open-less", "Open less", [("Start only what you can finish", "Pick one open loop and work it", "Do not open a new project today")], ("Define done", "Write what done means", "Stop when that line is met")),
                ("push", "Push to done", [("Close the loop", "Finish the thing you started", "Send it, file it, or ship it")], ("Refuse a new start", "Write the new idea down and return", "Do not let a new idea replace the finish")),
                ("cleanup", "Clean up", [("Finish an old loop", "Close something that has been open for days", "Decide to drop it if you will not finish it")], ("Leave a clean stop", "If it must continue, write the next action", "Do not leave a vague pile")),
                ("reputation", "Become someone who finishes", [("Finish in public", "Deliver what you said you would", "Tell the person it is done")], ("Start smaller next time", "Choose a finish you can reach today", "Complete it before you expand it")),
            ],
        ),
        _simple_direction(
            "reduce-noise",
            "Reduce noise",
            [
                ("silence", "Silence", [("Turn something off", "Silence notifications for a block", "Leave one chat closed")], ("Clear a surface", "Remove one source of noise from the desk", "Unsubscribe or mute one feed")),
                ("fewer", "Fewer inputs", [("Check once", "Open messages at a chosen time, not constantly", "Batch the inbox into one pass")], ("Protect a room", "Work somewhere quieter", "Use headphones or a closed door")),
                ("choose", "Choose the signal", [("Keep one input", "Read or watch one thing you chose", "Ignore the rest for the day")], ("Delete a habit of noise", "Do not open the noisiest app", "Move it off the first screen")),
                ("quiet-day", "Keep a quieter day", [("Start quiet", "Begin the day before the noise", "Do the important task first")], ("End quiet", "Stop scrolling before bed", "Write tomorrow's one signal")),
            ],
        ),
    ],
)

_ENTREPRENEUR = _identity(
    "entrepreneur",
    "Entrepreneur",
    [
        _simple_direction(
            "ship-every-day",
            "Ship every day",
            [
                ("slice", "Cut a slice", [("Ship something small", "Put one small improvement where a person can see it", "Send a draft today")], ("Define the slice", "Write what will be shipped before you build", "Make it smaller if it will not ship")),
                ("out", "Get it out", [("Publish the slice", "Release, send, or deploy it", "Do not keep polishing past the line")], ("Tell one user", "Show it to one person", "Ask what broke")),
                ("next-slice", "Ship the next", [("Ship again", "Put out the next small piece", "Fix one thing a person noticed")], ("Leave a trail", "Write what shipped", "Note what you will ship next")),
                ("cadence", "Keep the cadence", [("Ship on a dull day", "Send something even if it is modest", "Do not wait for a big launch")], ("Protect the making", "Spend a block building before you consume", "Close the tools that are not the ship")),
            ],
        ),
        _simple_direction(
            "talk-to-customers",
            "Talk to customers",
            [
                ("one-talk", "One conversation", [("Talk to one person", "Have a real conversation about their problem", "Write their words afterward")], ("Ask, don't pitch", "Ask what they do today", "Do not explain your idea first")),
                ("listen", "Listen", [("Hear the pain", "Ask where it costs them time or money", "Repeat back what you heard")], ("Find another", "Book or message the next person", "Do not stop at one friendly chat")),
                ("pattern", "See the pattern", [("Write the pattern", "Note what two people said in common", "Separate what you hoped from what they said")], ("Test a sentence", "Say the offer in their words", "Ask if that is the problem")),
                ("keep-talking", "Keep talking", [("Talk again", "Speak to someone new", "Follow up with someone you already met")], ("Use it", "Change one thing in the offer because of what you heard", "Do not build in silence")),
            ],
        ),
        _simple_direction(
            "build-the-offer",
            "Build the offer",
            [
                ("who", "Who it is for", [("Name the person", "Write who the offer is for", "Write the problem in their words")], ("Name the result", "Write what they get", "Cut any promise you cannot keep")),
                ("shape", "Shape it", [("Make it concrete", "Write what is included", "Set a price")], ("Make it buyable", "Put the offer where someone can say yes", "Remove one confusing part")),
                ("prove", "Prove it", [("Deliver it once", "Do the offer for one person", "Write what you had to invent on the fly")], ("Tighten it", "Remove a step they did not need", "Raise or hold the price on purpose")),
                ("offer-again", "Offer it again", [("Sell it again", "Send the offer to someone new", "Ask for the sale in a clear sentence")], ("Keep the promise", "Deliver what the offer said", "Write what you will not add")),
            ],
        ),
        _simple_direction(
            "show-up-on-the-work",
            "Show up on the work",
            [
                ("block", "A block of work", [("Work the business", "Spend 45 minutes on the business itself", "Do the task that moves it, not the task that feels busy")], ("Start on time", "Begin the block when you said", "Put the phone away")),
                ("priority", "The priority", [("Do the first thing first", "Finish the most important business task", "Do not start with email")], ("Leave a record", "Write what moved", "Write the next task")),
                ("consistency-work", "Consistency", [("Show up again", "Do the block on the next day", "Keep the same time")], ("Shrink rather than skip", "Do 20 minutes if the day collapses", "Do not zero the day")),
                ("owner", "Own it", [("Act like the owner", "Make one decision the business needs", "Do the uncomfortable task")], ("Close the day", "Stop at a set time", "Name tomorrow's first business task")),
            ],
        ),
    ],
)

_STRONG = _identity(
    "strong",
    "Strong",
    [
        _simple_direction(
            "train-consistently",
            "Train consistently",
            [
                ("session", "The session", [("Train", "Complete today's training session", "Do a full-body session for 30 minutes")], ("Arrive", "Start at the time you set", "Change into training clothes first")),
                ("repeat-train", "Repeat", [("Train again", "Do the next session you planned", "Repeat a session you know")], ("Log it", "Write the work you did", "Note one thing to keep")),
                ("easy-day", "The easy day", [("Do the light day", "Walk or move easily so you can train tomorrow", "Do the mobility you skip")], ("Do not invent a new program", "Follow the plan you wrote", "Leave the extra workout out")),
                ("standard-train", "The standard", [("Train when it is inconvenient", "Do the session anyway", "Shorten it rather than cancel")], ("Recover like it matters", "Sleep at the hour you set", "Eat a real meal after you train")),
            ],
        ),
        _simple_direction(
            "eat-to-support-training",
            "Eat to support training",
            [
                ("protein", "Protein", [("Eat for the session", "Include protein in the meal closest to training", "Do not train and then skip food")], ("Prepare it", "Have the meal ready before you are starving", "Shop or set aside what you need")),
                ("timing", "Timing", [("Eat at the right time", "Have a meal within a few hours of training", "Do not rely on random snacks")], ("Water", "Drink water through the training day", "Start the session hydrated")),
                ("enough-food", "Enough", [("Eat enough to recover", "Do not cut the meal that supports the work", "Add food if the session was hard")], ("Keep it simple", "Repeat a meal that works", "Do not chase a perfect diet")),
                ("match", "Match the work", [("Line food up with training", "Eat more on the training day than on the rest day story you tell yourself", "Write what you ate after the session")], ("Hold the line", "Skip the food that wrecks the next session", "Stop eating at the hour you set")),
            ],
        ),
        _simple_direction(
            "recover-on-purpose",
            "Recover on purpose",
            [
                ("down", "Downshift", [("Recover on purpose", "Take a slow walk", "Do ten quiet minutes of stretching")], ("Stop on time", "End the hard work when the plan says", "Do not add a junk session")),
                ("sleep-recover", "Sleep", [("Protect the night", "Go to bed at the recovery hour", "Keep the phone out of the bed")], ("Morning", "Get up without stealing the recovery", "Get daylight early")),
                ("sore", "Respect soreness", [("Move gently", "Walk instead of forcing the sore thing", "Train around pain, not through sharp pain")], ("Note it", "Write what hurts and what is only tired", "Adjust the next session")),
                ("ready", "Get ready again", [("Prepare the next effort", "Lay out the next session", "Eat and sleep so it can happen")], ("Keep recovery boring", "Repeat the same recovery habit", "Do not skip it because you feel fine")),
            ],
        ),
        _simple_direction(
            "keep-the-standard",
            "Keep the standard",
            [
                ("line", "The line", [("Meet the standard", "Do the session to the line you wrote", "Do not count a sloppy pass")], ("Show up", "Be there at the start time", "Begin without a long warm-up of excuses")),
                ("form", "The form", [("Keep the form", "Stop a set when the movement breaks", "Do the range you own")], ("Effort", "Work hard enough that it counts", "Leave one rep you could have faked")),
                ("honest", "Be honest", [("Record the truth", "Write what you actually did", "Do not inflate the session")], ("Fix one thing", "Correct one lazy habit in the session", "Ask for a better rep")),
                ("long", "Over the long run", [("Keep the standard on a bad day", "Do a clean short session", "Do not lower the line just to say you trained")], ("Repeat the standard", "Do it again the next session", "Treat the standard as normal")),
            ],
        ),
    ],
)

_CONSISTENT = _identity(
    "consistent",
    "Consistent",
    [
        _simple_direction(
            "keep-one-promise",
            "Keep one promise",
            [
                ("name-promise", "Name it", [("Keep one promise", "Do the one thing you promised yourself", "Write it where you can see it")], ("Do it early", "Finish it before the day fills up", "Do not trade it for a different task")),
                ("same", "The same promise", [("Keep it again", "Do the same promise today", "Do not redesign it")], ("Make it obvious", "Leave a cue for the promise", "Do it in the same place")),
                ("small", "Keep it small enough", [("Shrink it if you must", "Do a smaller version and count it", "Do not skip because the full version feels heavy")], ("Mark it", "Note that you kept it", "Do not rely on memory")),
                ("ordinary-promise", "Make it ordinary", [("Keep it without motivation", "Do the promise on a flat day", "Start before you want to")], ("Set the next one", "Write tomorrow's promise tonight", "Keep the chain of one")),
            ],
        ),
        _simple_direction(
            "same-time-every-day",
            "Same time every day",
            [
                ("hour-set", "Set the hour", [("Show up at the hour", "Start at the time you chose", "Set an alarm and obey it")], ("Prepare the hour", "Clear the five minutes before it", "Put what you need in place")),
                ("defend", "Defend the hour", [("Do not move it", "Decline one thing that would shift the hour", "Start even if you are late, at the task")], ("Stay for it", "Remain for the whole block", "Stop at the end so tomorrow is possible")),
                ("repeat-hour", "Repeat the hour", [("Be there again", "Keep the same hour", "Do not renegotiate it in the morning")], ("Track the misses", "Write it down if you missed the hour", "Return at the hour the next day")),
                ("identity-hour", "Become the hour", [("Arrive without debate", "Sit down when the hour hits", "Treat it as already decided")], ("Protect tomorrow's hour", "Do not schedule over it", "Go to bed so you can make it")),
            ],
        ),
        _simple_direction(
            "dont-miss-twice",
            "Don't miss twice",
            [
                ("return", "Return", [("Do not miss twice", "If you missed, do it today", "Start with a smaller version")], ("Name the miss", "Write that you missed, without a speech", "Do the thing anyway")),
                ("quick", "Make the return quick", [("Return the same day you notice", "Do it before the day ends", "Do not schedule the return for next week")], ("Remove the drama", "Do not compensate with a huge session", "Just do today's version")),
                ("setup-return", "Make missing harder", [("Set a cue", "Leave a reminder you will see", "Tell someone you are back")], ("Do the minimum", "Complete the smallest honest version", "Mark it done")),
                ("stay-back", "Stay back", [("String two days", "Do it again the day after you returned", "Keep the version small until it is stable")], ("Don't negotiate the second miss", "Treat a second miss as the thing to avoid", "Start before you explain")),
            ],
        ),
        _simple_direction(
            "stack-the-week",
            "Stack the week",
            [
                ("today-stack", "Today", [("Add today", "Complete the daily action", "Do it even if the week already slipped")], ("Write the stack", "Mark the day on a simple row", "Do not hide a miss")),
                ("next", "The next day", [("Add another", "Do the action again", "Keep it the same action")], ("Look at the row", "See the days you have", "Do not restart the week because of one gap")),
                ("middle", "The middle of the week", [("Keep the middle", "Do the action on the ordinary weekday", "Do not save it for a perfect day")], ("Shrink the weekend excuse", "Plan the weekend version now", "Make it shorter, not optional")),
                ("full", "A full stack", [("Close the week", "Do today's action", "Count how many days you actually did")], ("Set next week", "Write the same action for next week", "Do not add a second action yet")),
            ],
        ),
    ],
)

_MENTALLY_RESILIENT = _identity(
    "mentally-resilient",
    "Mentally Resilient",
    [
        _simple_direction(
            "sit-with-discomfort",
            "Sit with discomfort",
            [
                ("stay-feel", "Stay", [("Stay with it", "Sit for five minutes with a feeling you want to escape", "Do not fix it, scroll it, or eat it")], ("Name the body", "Notice where it sits in the body", "Breathe slowly until the five minutes end")),
                ("urge", "The urge", [("Let an urge pass", "Wait ten minutes before you obey it", "Do something plain while you wait")], ("Return", "Come back when you notice you left", "Start the five minutes again")),
                ("hard-moment", "A hard moment", [("Stay in a hard moment", "Do not leave the conversation or the task at the peak", "Finish the minute you are in")], ("Soften", "Relax your jaw and shoulders", "Keep going without making it mean more")),
                ("choose-stay", "Choose to stay", [("Practice on purpose", "Pick a discomfort and stay with it briefly", "Write what you did instead of escaping")], ("Keep your word", "Do the thing after the feeling, not before it leaves", "Start while it is still there")),
            ],
        ),
        _simple_direction(
            "name-the-thought",
            "Name the thought",
            [
                ("label", "Label it", [("Name the thought", "Write the sentence your mind is repeating", "Call it a thought, not a fact")], ("Leave it on the page", "Do not argue with it for more than a minute", "Return to the task")),
                ("again-name", "Name another", [("Catch the next one", "Label one more thought today", "Notice the story you tell about yourself")], ("Separate", "Write 'I am having the thought that…'", "Then do the next action")),
                ("pattern-thought", "See the pattern", [("Find the repeat", "Write a thought you have had before", "Note what it tells you to avoid")], ("Do the opposite once", "Take one step the thought said not to", "Keep it small")),
                ("quiet-mind", "Let it be loud", [("Work beside it", "Do a block of work while the thought is still there", "Do not wait to feel clear")], ("Close the page", "Stop rereading the thought", "End the day without solving your whole mind")),
            ],
        ),
        _simple_direction(
            "return-to-the-work",
            "Return to the work",
            [
                ("back", "Come back", [("Return to the work", "When you drift, come back once", "Touch the task before you touch the phone")], ("Make the return small", "Do five minutes after you return", "Do not demand a perfect restart")),
                ("cue-return", "Use a cue", [("Set a return point", "Choose a time to come back", "Come back at that time")], ("Drop the guilt", "Do not spend the return explaining the drift", "Start")),
                ("longer", "Stay longer", [("Stay after you return", "Work for a real block", "Write where you will return next")], ("One tab", "Keep only the work open", "Close the drift")),
                ("identity-return", "Be someone who returns", [("Return on a bad day", "Come back even if the morning was lost", "Do the smallest piece")], ("Count returns", "Write that you came back", "Treat the return as the practice")),
            ],
        ),
        _simple_direction(
            "end-the-day-clean",
            "End the day clean",
            [
                ("close-day", "Close", [("End on purpose", "Stop work at the time you set", "Write the one line the day needs")], ("Clear a small mess", "Leave one surface ready for tomorrow", "Do not reopen the whole day")),
                ("mind", "Set the mind down", [("Put the thoughts somewhere", "Write what is unfinished", "Do not carry it into the bed")], ("Forgive the miss", "Note what you did not do, then stop", "Do not rehearse it")),
                ("body-end", "Let the body end", [("Signal the end", "Dim the lights or wash your face", "Leave the phone outside the routine")], ("Keep a kind hour", "Do not start a hard talk at the end", "Read or sit instead of scrolling")),
                ("tomorrow-clean", "Leave tomorrow possible", [("Name the first step", "Write tomorrow's first action", "Make it small enough to start")], ("Go to bed", "Keep the bedtime", "Treat sleep as part of the work")),
            ],
        ),
    ],
)

_PRODUCTIVE = _identity(
    "productive",
    "Productive",
    [
        _simple_direction(
            "one-important-thing",
            "One important thing",
            [
                ("choose-one", "Choose one", [("Do the important thing", "Finish a real piece of the most important task", "Do it before the smaller tasks")], ("Name it first", "Write the one thing before you open anything", "Do not pick three")),
                ("protect-one", "Protect it", [("Give it a block", "Spend 45 minutes on that one thing", "Silence what competes")], ("Stop when it moves", "Reach the line you wrote", "Do not dilute it with extras")),
                ("again-one", "Do it again", [("Pick tomorrow's one thing", "Write it before the day ends", "Do today's before you redesign the system")], ("Ignore the fake urgent", "Let one noisy task wait", "Return to the important thing")),
                ("measure", "Measure by the one thing", [("Count the day by it", "Ask whether the one thing moved", "Do a short version if the day broke")], ("Keep the bar", "Do not call a busy day successful if the one thing did not move", "Write what blocked it")),
            ],
        ),
        _simple_direction(
            "time-box-the-work",
            "Time-box the work",
            [
                ("box", "Set a box", [("Work inside a box", "Set a timer and work until it ends", "Stop when it ends")], ("One box, one task", "Write the task on the box", "Do not change the task mid-box")),
                ("second-box", "Another box", [("Run a second box", "Do another timed block", "Take a short break between them")], ("Respect the end", "Do not bleed the box into the next hour", "Write what is left")),
                ("honest-box", "Be honest about the box", [("Use a length you will keep", "Choose 25 or 50 minutes and obey it", "If you stop early, write why")], ("Park the rest", "Capture new tasks outside the box", "Do not chase them yet")),
                ("day-of-boxes", "A day of boxes", [("Box the important work first", "Run the first box before email", "Box one admin task later, not first")], ("Review the boxes", "Note how many you actually ran", "Set tomorrow's first box")),
            ],
        ),
        _simple_direction(
            "close-open-loops",
            "Close open loops",
            [
                ("list-loops", "List them", [("See the open loops", "Write the loops that are taking space", "Pick one to close")], ("Close one", "Finish, send, or cancel that loop", "Do not open a replacement")),
                ("small-closes", "Close small ones", [("Close a small loop", "Answer, file, or throw away one thing", "Make the decision that has been waiting")], ("Empty a pile", "Clear one physical or digital pile", "Stop at the end of that pile")),
                ("kill", "Kill or finish", [("Decide", "Finish it or consciously drop it", "Tell the person if they are waiting")], ("Capture the rest", "Put remaining loops on one list", "Do not keep them in your head")),
                ("fewer-opens", "Open fewer", [("Close before you open", "Do not start a new loop until one is closed", "Finish the day's chosen loop")], ("End with fewer", "Leave the day with one less open loop", "Write the first loop for tomorrow")),
            ],
        ),
        _simple_direction(
            "protect-deep-hours",
            "Protect deep hours",
            [
                ("hours", "The hours", [("Guard the deep hours", "Keep a two-hour window free of meetings", "Spend it on the hard work")], ("Start clean", "Begin with the work, not the inbox", "Close the extra tabs")),
                ("defend-hours", "Defend them", [("Say no once", "Decline or move one thing that would enter the hours", "Tell someone the hours are taken")], ("Stay inside", "Do not leave the work for a small ping", "Write the ping down")),
                ("use", "Use them well", [("Do the deepest task", "Spend the hours on the task that needs thought", "Produce something by the end")], ("Recover the edge", "Take a real break at the end", "Do not fill the break with more noise")),
                ("keep-hours", "Keep them tomorrow", [("Book them again", "Put the next deep hours on the calendar", "Do not give them away tonight")], ("Show up to them", "Be there at the start", "Do the work even if you feel flat")),
            ],
        ),
    ],
)

IDENTITIES: tuple[CatalogIdentity, ...] = (
    _DISCIPLINED,
    _FINANCIALLY_INDEPENDENT,
    _HEALTHY,
    _CONFIDENT,
    _FOCUSED,
    _ENTREPRENEUR,
    _STRONG,
    _CONSISTENT,
    _MENTALLY_RESILIENT,
    _PRODUCTIVE,
)

_BY_ID = {identity.id: identity for identity in IDENTITIES}


def list_identities() -> tuple[CatalogIdentity, ...]:
    return IDENTITIES


def find_identity(identity_id: str) -> CatalogIdentity | None:
    return _BY_ID.get(identity_id)


def find_direction(identity: CatalogIdentity, direction_id: str) -> CatalogDirection | None:
    for direction in identity.directions:
        if direction.id == direction_id:
            return direction
    return None


def _validate() -> None:
    seen: set[str] = set()
    for identity in IDENTITIES:
        if not identity.directions:
            raise RuntimeError(f"{identity.id} has no directions")
        for direction in identity.directions:
            if len(direction.phases) != 4:
                raise RuntimeError(f"{direction.id} does not have four phases")
            for phase in direction.phases:
                if phase.id in seen:
                    raise RuntimeError(f"Duplicate phase id {phase.id}")
                seen.add(phase.id)
                bases = [item for item in phase.commitments if item.unlock_streak == 0]
                extras = [item for item in phase.commitments if item.unlock_streak == EXTRA_UNLOCK_STREAK]
                if not bases or len(extras) != 1:
                    raise RuntimeError(f"{phase.id} needs base commitments and one extra")
                for commitment in phase.commitments:
                    if not commitment.implementations:
                        raise RuntimeError(f"{commitment.id} has no implementations")
                    if commitment.id in seen:
                        raise RuntimeError(f"Duplicate commitment id {commitment.id}")
                    seen.add(commitment.id)


_validate()
