# game.py
import os
import sys
import time
from contextlib import contextmanager

if os.name == "nt":
    import ctypes

from state import (
    load_state, save_state, update_state,
    mark_location_visited, is_first_visit,
    notice_rose, can_access_queens_room,
    can_access_sealed_corridor,
    update_archivist_stage, evaluate_asur_interaction,
    check_three_accounts, check_investigation_complete,
    trigger_punishment_consequence
)
from prompts import generate_notebook
from ollama_client import (
    get_response, end_conversation, reset_all_conversations,
    get_history_length, inject_context_reminder,
    evaluate_young_asur_response, stream_text
)

# grafičko sučelje

WIDTH = 47

def divider():
    print("─" * WIDTH)

def header(title):
    print("═" * WIDTH)
    print(f" {title}")
    print("═" * WIDTH)

def clear():
    os.system("cls" if os.name == "nt" else "clear")

# skip dugme
# Jedan dodir space tipke preskače jedan blok, a držanje space tipke preskače cijelu sekciju

HOLD_THRESHOLD = 0.85


class NarrativeController:
    def __init__(self):
        self.fast_forward = False
        self.section_depth = 0

    def begin_section(self):
        if self.section_depth == 0:
            self.fast_forward = False
        self.section_depth += 1

    def end_section(self):
        if self.section_depth > 0:
            self.section_depth -= 1

        if self.section_depth == 0:
            if self.fast_forward and os.name == "nt":
                while self.space_is_down():
                    time.sleep(0.01)
            self.fast_forward = False

    def space_is_down(self):
        if os.name == "nt":
            return bool(ctypes.windll.user32.GetAsyncKeyState(0x20) & 0x8000)
        return False

    def wait_for_space_action(self):
        """
        Wait for a Space press and distinguish a tap from a hold.
        Returns True when the current operation should be skipped.
        """
        if not self.space_is_down():
            return False

        started = time.monotonic()

        while self.space_is_down():
            if time.monotonic() - started >= HOLD_THRESHOLD:
                self.fast_forward = True
                return True
            time.sleep(0.01)

        
        return True

    def skip_requested(self):
        if self.fast_forward:
            return True
        return self.wait_for_space_action()


narrative = NarrativeController()


@contextmanager
def narrative_section():
    """Create a self-contained block of narrative text/cinematic timing."""
    narrative.begin_section()
    try:
        yield
    finally:
        narrative.end_section()


def interruptible_sleep(seconds):
    """Sleep inside a narrative section, with Space-based skipping."""
    if narrative.section_depth == 0:
        time.sleep(seconds)
        return

    if narrative.fast_forward:
        return

    end_time = time.monotonic() + seconds
    while time.monotonic() < end_time:
        if narrative.skip_requested():
            return
        time.sleep(min(0.01, end_time - time.monotonic()))


def pause():
    # tvrde pauze ne ulaze u input
    narrative.end_section()
    input("\n[Press Enter to continue]")


def _slow_print(text, delay=0.018):
    """Internal typewriter implementation."""
    if narrative.fast_forward:
        print(text)
        return

    for i, char in enumerate(text):
        if narrative.skip_requested():
            sys.stdout.write(text[i:])
            sys.stdout.flush()
            print()
            return

        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)

    print()


def slow_print(text, delay=0.018):
    """Print text with tap-to-skip and hold-to-fast-forward behavior."""
    if narrative.section_depth == 0:
        with narrative_section():
            _slow_print(text, delay)
    else:
        _slow_print(text, delay)


def print_wrapped(text, width=WIDTH - 2):
    """
    Print wrapped narrative as one fast-forwardable section.

    A Space tap finishes the current line. Holding Space long enough
    finishes the current line and prints the rest of this wrapped block
    instantly. The fast-forward state is reset when the block ends.
    """
    with narrative_section():
        paragraphs = text.split("\n\n")
        for i, para in enumerate(paragraphs):
            words = para.split()
            line = " "
            for word in words:
                if len(line) + len(word) + 1 > width:
                    slow_print(line)
                    line = f" {word}"
                else:
                    line = f"{line} {word}" if line.strip() else f" {word}"
            if line.strip():
                slow_print(line)
            if i < len(paragraphs) - 1:
                print()


# LOCATION DESCRIPTIONS
# Each location has a first visit and return visit
# description. Some have changed state descriptions
# triggered by specific state conditions.
# Blood roses are embedded in first visit descriptions.
# Edmund notices them. He does not mention them.

LOCATIONS = {

    "archive": {

        "first": """
The archive occupies a wing of the palace that the 
main corridors seem to route around rather than 
through. The smell is of old paper and 
something mineral underneath it, the particular 
atmosphere of a space that has been consistently 
maintained for longer than most people in the palace 
have been alive.

The shelves are dense and organized according to 
a system that is not immediately legible. 
At the base of the oldest shelf, where the stone floor 
meets the wood, something grows in the gap. 
Small. Deep red. You do not look at it for long.

The archivist does not look up when you enter,
he's seemingly entranced in whatever he's doing.
""",

        "return": """
The archive.
The archivist is present, but he does not 
acknowledge your arrival.
In fact, he acknowledges very little 
that is not the work in front of him.
""",

        "consequence": """
The archive. The archivist's chair is empty. His 
cataloguing from this morning is half finished on 
the desk, exactly as he left it.
The work seems to have stopped where he had stopped.

At the base of the oldest shelf the red thing in 
the gap has grown slightly since your last visit. 
You are not certain it was there before today.

Actually, you definitely are certain that it was.
""",
    },

    "physicians_quarters": {

        "first": """
The physician's quarters occupy a practical space 
near the palace's residential wing which is close enough 
to reach quickly, but removed enough for discretion. 
The room is ordered in the specific way of someone 
who does not trust disorder to not become urgency.

Instruments are laid out on a cloth in precise 
arrangement. Ledgers line one shelf with spines 
outward, their years visible. He has been keeping 
records here for twenty two years. The record of 
those years is physically present in this room.

He looks up when you enter, he was expecting 
someone eventually.
""",

        "return": """
The physician's quarters. He sets down 
whatever he was doing with the deliberate care of 
someone who does not leave things mid-task.
""",

        "consequence": """
The physician's quarters. Something 
in his manner is different from your last visit, 
the professional warmth is present but it is working 
harder than before. Handling something considerably 
more fragile.

He doesn't seem adamant on mentioning it.
""",
    },

    "ceremonial_offices": {

        "first": """
The ceremonial offices are the most formally 
maintained spaces in the palace outside of the 
reception hall itself.
The master of ceremonies has been in this room for thirty eight years 
and it shows in the particular way a space shows 
the person who has inhabited it with complete 
attention for a very long time.

Every surface is functional.
Nothing is decorative that is not also load-bearing. 
The calendar on the wall accounts for the next six months of 
formal palace life in handwriting so consistent 
it reads as printed.

She looks up when you enter. She does not look 
pleased for you may be the only disruption to her routine currently.
""",

        "return": """
The ceremonial offices. She is at her desk. She 
looks up. The expression is the same as last time. 
You are still not on her calendar.
""",

        "consequence": """
The ceremonial offices. She looks up when you 
enter. The expression has changed. You have been 
recategorized. Not from dislike to something warmer. 
From anomaly to liability.

She still sees you, but doesn't seem as cooperative.
""",
    },

    "heralds_post": {

        "first": """
The herald's post is a narrow room near the main 
correspondence office, a functional space for a 
functional role, furnished with only what the work 
requires. A small desk, and a routing ledger. A coat 
hook with a palace-issue cloak that has seen 
considerable use.

He is sorting correspondence when you arrive.
He looks up with the open expression of someone who 
has not yet learned to adjust his face accordingly to an
unknown visitor.
""",

        "return": """
The herald's post. He is here. He looks up with 
slightly more wariness than last time, not much, 
but he is learning.
""",

        "consequence": """
The herald's post. He is here. He looks up and 
something in his manner is different. He is being 
careful in a way that did not come naturally before. 
It sits on him like a coat he is not used to wearing. 

He nods at you. 
He does not say anything first. 
""",
    },

    "groundskeepers_store": {

        "first": """
The groundskeeper's store is in the lower eastern 
section of the palace where the maintenance 
infrastructure lives. The spaces that keep 
everything else functioning and that appear on 
no official tour. It smells of stone and oil 
and the particular dust of places that accumulate 
it on purpose.

He is here. He is doing something with a length 
of rope and a metal fitting that appears to require 
complete attention, 
he gives you half of it.
""",

        "return": """
The groundskeeper's store. He is here. He seems to be
giving you the same amount of attention as last time. 
""",
    },

    "eastern_wing": {

        "first": """
The eastern wing is the part of the palace that 
the palace does not quite include in itself anymore. 
The maintenance is correct because the groundskeeper 
sees to that, but the atmosphere has the specific 
quality of spaces that were once inhabited and 
are visibly no longer.

The corridor runs to a sealed door at the far end. 
The wax is wrong. Not the age of the decree wrong. 
Recently wrong. The emblem pressed into it belongs 
to a period that postdates the sealing order.

In the corner near the floor, where the stone 
meets the skirting, something red is growing.
""",

        "return": """
The eastern wing corridor. The sealed door at 
the end. The wax is as you left it, it's recently 
wrong, correctly presented.
""",

        "consequence": """
The eastern wing corridor. The sealed door. 

The wax has been replaced since your last visit. 
New wax. Current emblem. Done properly this time 
by someone who knew what properly looked like.

The red thing in the corner near the floor has 
grown. You do not look at it for long.
""",
    },

    "sealed_corridor": {

        "first": """
Beyond the door the corridor is exactly what 
a sealed space becomes over time, the dust 
has its own history here, layered and disturbed 
in patterns that are not random.
Someone has been this way. 
More than once. 
Carefully, but not carefully enough 
for someone paying attention to miss.

The door to the queen's chambers is at the end. 
The seal on this one is older. This one has not 
been replaced.

You are standing in a space that the palace 
considers does not exist for current purposes. 
It exists.
""",

        "return": """
The sealed corridor. The dust. The door to 
the queen's chambers at the end.
""",
    },

    "queens_chambers": {

        "first": """
The room is not what you expected at first and then it is 
exactly what you expected.

It has been sealed and it has been visited.
Both of these things are present simultaneously in the 
specific way of a space that has been maintained 
by someone who could not let it be purely sealed. 
Objects left in their positions but not dusty in 
the way the positions suggest they should be. 
A child's drawings arranged on a surface that 
was not their original location.

There are red flowers in the corner. Not growing from 
anything. Present in the way that things are 
sometimes simply present in rooms that have held 
a great deal over a long time.

You open your notebook. You begin to work.
""",

        "return": """
The queen's chambers. The drawings. The documents 
in the secondary space adjacent. The flowers in 
the corner that you have stopped not mentioning 
to yourself even if you do not write them down.
""",

        "consequence": """
The queen's chambers. 

Something has been moved since your last visit. 
Rearranged in the specific 
way of someone who was looking for something 
and found it and left evidence of the finding 
in the rearrangement.

The drawings are still here. They are in the 
same positions as before.

You do not know if this means they were not 
what was looked for or if what was looked for 
was found elsewhere in the room. You add this 
to the notebook without conclusion.

The red flowers in the corner seem to have grown in the meantime.
""",
    },

    "courtyard": {

        "first": """
The palace courtyard is a formal space, flagstones, 
a central basin, corridors opening on three sides. 
It is used for morning movement and certain 
ceremonial transitions and, apparently, for a 
prince who has found that the open air is one 
of the few spaces in the palace where the walls 
are not immediately suffocating.

He is in the far corner. 
He has noticed you, but has not moved.
""",

        "return": """
The courtyard. He is here, or he is not. 
The corner where he stands when he is here 
is visible from the entrance.
""",

        "consequence": """
The courtyard. He is here.

He is standing in his corner with the same 
stillness as always. It is a different stillness 
than before. The same posture. Something behind 
it has changed in the specific way that things 
change in people when something else has been 
removed from their world and they have absorbed 
it into the stillness rather than letting it 
show as anything that could be seen and used.

He watches you cross the courtyard toward him.
""",
    },

    "reception_hall": {

        "first": """
The reception hall is where the king's presence 
is made architectural. The proportions are designed 
to produce a specific effect in anyone standing 
in them, the ceiling is too high, the distances 
too managed, the light controlled in ways that 
ensure the person at the far end of the room 
is always seen correctly.

The king is not here. His absence has the same 
quality as his presence likely would. 
You feel the room was designed around a center of gravity 
that you are not and will not be.

A functionary near the door informs you that 
the authentication task has been assigned and 
your access to relevant palace areas authorized. 
He hands you a document. He does not look at you 
while doing so. Nobody in this room looks at 
things that are not the king.
""",

        "return": """
The reception hall. The king is not here. 
His absence occupies the room with the same 
weight as his presence would.
""",

        "consequence": """
The reception hall. The king is not here.

A different functionary is near the door today. 
The previous one is not mentioned.

The room is the same. The gravity at its center 
is the same. You have reported to that gravity 
and it has acted on what you reported. 
The room does not look different because of this.

You leave quickly.
""",
    },
}


def get_location_description(location_key, state):
    """
    Returns the appropriate description for a location
    based on visit history and current state.
    """
    loc = LOCATIONS.get(location_key)
    if not loc:
        return "You are somewhere in the palace."

    # provjeri consequence
    if state["punishment_consequence_triggered"]:
        if "consequence" in loc:
            return loc["consequence"].strip()

    # je li prvi posjet
    if is_first_visit(state, location_key):
        # ruže primjećene
        rose_locations = {
            "archive": "Base of the oldest shelf in the archive",
            "eastern_wing": "Corner of the eastern wing corridor",
            "queens_chambers": "Corner of the queen's chambers",
        }
        if location_key in rose_locations:
            state = notice_rose(
                state, rose_locations[location_key]
            )
        return loc["first"].strip()

    return loc["return"].strip()


# NAVIGATION MENU

LOCATION_NAMES = {
    "reception_hall":      "The reception hall",
    "archive":             "The archive",
    "physicians_quarters": "The physician's quarters",
    "ceremonial_offices":  "The ceremonial offices",
    "heralds_post":        "The herald's post",
    "groundskeepers_store":"The groundskeeper's store",
    "eastern_wing":        "The eastern wing",
    "sealed_corridor":     "The sealed corridor",
    "queens_chambers":     "The queen's chambers",
    "courtyard":           "The courtyard",
}

AGENT_FOR_LOCATION = {
    "archive":             "archivist",
    "physicians_quarters": "physician",
    "ceremonial_offices":  "master",
    "heralds_post":        "herald",
    "groundskeepers_store":"groundskeeper",
    "courtyard":           "young_asur",
}

REPORTING_LOCATION = "reception_hall"


def get_available_locations(state):
    """
    Returns list of location keys currently accessible.
    Sealed spaces require progression gates.
    """
    available = [
        "reception_hall",
        "archive",
        "physicians_quarters",
        "ceremonial_offices",
        "heralds_post",
        "groundskeepers_store",
        "eastern_wing",
        "courtyard",
    ]

    if can_access_sealed_corridor(state):
        available.append("sealed_corridor")

    if can_access_queens_room(state):
        available.append("queens_chambers")

    return available


def show_navigation_menu(current_location, state):
    """Display navigation options from current location."""
    available = get_available_locations(state)

    print()
    divider()
    print(" WHERE TO GO")
    divider()

    # bez trenutne lokacije
    options = [
        loc for loc in available
        if loc != current_location
    ]

    for i, loc in enumerate(options, 1):
        name = LOCATION_NAMES[loc]
        # neposjećene lokacije imaju zvjezdicu
        marker = " *" if is_first_visit(state, loc) else "  "
        print(f" [{i}]{marker}{name}")

    print()
    print(" [N] Open notebook")
    print(" [Q] Save and quit")
    divider()

    return options


def navigate(state):
    """Main navigation loop. Returns updated state."""

    current_location = "reception_hall"

    while True:
        clear()
        header(LOCATION_NAMES[current_location].upper())

        # ispis opisa lokacije
        description = get_location_description(
            current_location, state
        )
        print()
        print_wrapped(description)

        
        state = mark_location_visited(state, current_location)

        
        state = handle_location_logic(current_location, state)

        # jel gotovo
        state = check_investigation_complete(state)
        if state["investigation_complete"]:
            state = trigger_ending(state)
            return state

        print()
        divider()
        print(" WHAT NOW")
        divider()

        
        actions = get_location_actions(current_location, state)
        for key, description in actions.items():
            print(f" [{key}] {description}")

        print()
        nav_options = show_navigation_menu(
            current_location, state
        )

        choice = input("\n> ").strip().upper()

        
        if choice == "Q":
            save_state(state)
            print()
            slow_print(" Progress saved. Edmund waits.")
            interruptible_sleep(1)
            sys.exit()

        elif choice == "N":
            show_notebook(state)

        elif choice in actions:
            state = handle_action(
                choice, current_location, state
            )

        else:
            
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(nav_options):
                    current_location = nav_options[idx]
                else:
                    slow_print(" That option is not available.")
                    interruptible_sleep(0.8)
            except ValueError:
                slow_print(" Edmund considers this. Nothing happens.")
                interruptible_sleep(0.8)


def get_location_actions(location, state):
    """
    Returns dict of available actions at current location.
    Keys are single letter/number strings shown to player.
    Values are description strings.
    """
    actions = {}

    # Speaking to an agent
    if location in AGENT_FOR_LOCATION:
        agent = AGENT_FOR_LOCATION[location]
        agent_names = {
            "archivist":     "the archivist",
            "physician":     "the physician",
            "master":        "the master of ceremonies",
            "herald":        "the junior herald",
            "groundskeeper": "the groundskeeper",
            "young_asur":    "the prince",
        }

        
        if agent == "archivist" and \
           state["punishment_consequence_triggered"]:
            pass  
        else:
            name = agent_names[agent]
            spoke_key = f"spoke_to_{agent}"
            if state.get(spoke_key):
                actions["S"] = f"Continue speaking with {name}"
            else:
                actions["S"] = f"Speak with {name}"

    
    if location == "archive" and \
       state["edmund_has_authentication_task"] and \
       not state["edmund_found_gap_in_document"]:
        actions["E"] = "Examine the authentication document"

    # Accessing the older maps in the archive
    if location == "archive" and \
       state["archivist_gave_older_maps"] and \
       not state["edmund_has_translated_address"]:
        actions["M"] = "Study the older maps"

    # Examining the sealed corridor door
    if location == "eastern_wing":
        actions["E"] = "Examine the door seal"

    # Entering the queen's chambers actions
    if location == "queens_chambers":
        if not state["edmund_found_mementos"]:
            actions["E"] = "Examine the room's contents"
        if state["edmund_found_mementos"] and \
           not state["player_reported_to_king"] and \
           not state["punishment_consequence_triggered"]:
            actions["R"] = "Record findings in notebook"

    # Reporting to the king
    if location == "reception_hall" and \
       state["edmund_found_mementos"] and \
       not state["player_reported_to_king"]:
        actions["P"] = "Present findings to the king"

    return actions


def handle_location_logic(location, state):
    """
    Handles automatic state updates triggered by
    arriving at a location. Returns updated state.
    """

    # Authentication task assigned on first reception hall visit
    if location == "reception_hall" and \
       not state["edmund_has_authentication_task"]:
        state = update_state(
            state, "edmund_has_authentication_task", True
        )

    # Mark queen's room as entered
    if location == "queens_chambers" and \
       not state["edmund_entered_queens_room"]:
        state = update_state(
            state, "edmund_entered_queens_room", True
        )
        # Check if this unlocks archivist stage 4
        state = update_archivist_stage(state)

    return state


def handle_action(action, location, state):
    """
    Handles non-navigation, non-dialogue actions.
    Returns updated state.
    """

    # Examine the authentication document
    if action == "E" and location == "archive":
        clear()
        header("THE AUTHENTICATION DOCUMENT")
        print()
        print_wrapped("""
The document is old but not fragile. It has been 
handled carefully across its life. The primary 
text is dense with lineage records, property claims, 
the administrative language of establishing 
legitimate inheritance.

You read it the way you read everything, not skipping a thing,
for there has to be a pattern in everything. 

You read, including the parts that were not meant to be read 
carefully.

There is a gap. A person referenced by role, the 
reader to the queen's household who appears once 
in the secondary witness records and nowhere else 
in any document you have been given access to. 
The reader then wasn't removed, he was simply never given a name anywhere 
the record extends.

You make a note.


Then you find the annotation in the margin. 
A different hand with lighter pressure on the paper, 
added after the primary text was dry. 
A location, written as if someone needed to record it quickly on 
the nearest available surface.

The location doesn't seem to correspond to anything 
in the current city's geography.

You make another note.
""")
        state = update_state(
            state, "edmund_found_gap_in_document", True
        )
        state = update_state(
            state, "edmund_found_marginal_annotation", True
        )
        
        state = update_archivist_stage(state)
        pause()

    # m posebna akcija
    elif action == "M" and location == "archive":
        clear()
        header("THE OLDER MAPS")
        print()
        print_wrapped("""
The archivist has provided maps of the city from 
before the current street layout, from before the 
civic restructuring that demolished entire districts 
and built new ones over their foundations.

You cross reference the annotation's location 
against each successive map working backwards. 
The current map shows nothing. The map from two 
centuries prior shows nothing. The map from four 
centuries prior...

There. A building. A specific address in a district 
that was demolished in the civic restructuring of 
that period. The annotation references a location 
that did not exist in the city at the time the 
document was written.

Whoever wrote the annotation was working from 
knowledge of a geography that predates the document 
by centuries.

You translate the location into terms you can 
carry with you. You write them down carefully. 
You write them twice.
""")
        state = update_state(
            state, "edmund_has_older_maps", True
        )
        state = update_state(
            state, "edmund_has_translated_address", True
        )
        state = check_three_accounts(state)
        state = check_investigation_complete(state)
        pause()

    
    elif action == "E" and location == "eastern_wing":
        clear()
        header("THE DOOR SEAL")
        print()
        print_wrapped("""
You examine it closely. The wax is wrong in some way, not the age of the decree wrong, 
not deterioration wrong, but recently replaced kind of wrong. 
The emblem pressed into it belongs to the current 
period's official sigil. The sealing decree predates 
that sigil by years.

Someone resealed this door after it had been 
opened. Someone who had access to current official 
materials and sufficient authority to use them. 
Someone who assumed nobody would look closely 
enough to notice the dates did not cohere.

You add this to the notebook without conclusion.
""")
        pause()

    # Examine the queen's room contents
    elif action == "E" and location == "queens_chambers":
        clear()
        header("THE ROOM'S CONTENTS")
        print()
        print_wrapped("""
The drawings are a child's, made with materials 
that were brought here rather than found here, 
cared for in the specific way of things that 
matter to someone who has nowhere else to put 
what matters to them.

There are other small and personbal objects. 
The kind of things that accumulate around a person 
over time and that become illegible as objects 
once the person is gone but remain present as 
evidence of the presence.

In the secondary space adjacent to the main 
chamber there is a document collection. You 
examine it. Among the official papers there are lineage 
records, correspondence, administrative documents 
from the queen's household, there is something 
that is not official. A record in a child's hand. 
Careful for a child's hand. More careful than 
a child usually is.

You read what you can. You cannot read all of it. 
What you can read is enough to understand what 
kind of thing it is and what it cost to make it.

You close it. You leave it where it is. 
You make a note in your own notebook that 
says only: witnessed. kept.
""")
        state = update_state(
            state, "edmund_found_mementos", True
        )
        state = update_state(
            state, "edmund_found_record", True
        )
        pause()

    
    elif action == "R" and location == "queens_chambers":
        clear()
        header("RECORD FINDINGS")
        print()
        print_wrapped("""
You have found something that belongs to the 
prince, the something being mementos left for his mother, a private 
record of things he has witnessed. This information 
is in your possession now.

You consider what to do with it.

You can present these findings to the king as 
part of your authentication task. He assigned 
you to investigate and report. This falls within 
that remit by a certain reading of it.

Or you can record it in your own notebook and 
tell him nothing about this room or what it 
contains.
""")
        print()
        divider()
        print(" [1] Add to official report for the king")
        print(" [2] Record in personal notebook only")
        divider()
        choice = input("\n> ").strip()

        if choice == "1":
            state = update_state(
                state, "player_reported_to_king", True
            )
            clear()
            print()
            print_wrapped("""
You add it to the report. It is thorough. 
It is complete. You are doing your job.
""")
            pause()
        else:
            clear()
            print()
            print_wrapped("""
You close your notebook. Some things belong 
to the notebook and some things belong to 
the room they were found in. You leave this 
one where it is.
""")
            pause()

    # Present findings to the king
    elif action == "P" and location == "reception_hall":
        clear()
        header("THE KING'S RECEPTION")
        print()
        print_wrapped("""
The functionary takes your report. He does not 
read it in front of you. He informs you it will 
be reviewed and that your access authorization 
remains valid for the duration of your task.

You leave the reception hall. You do not know 
what has been set in motion. You know what 
you put in the report. The rest is the king's 
arithmetic.
""")
        state = trigger_punishment_consequence(state)
        pause()

        
        clear()
        print()
        print_wrapped("""
You learn what happened later
through the specific atmospheric change that 
moves through a palace when something has been 
done quietly that cannot be undone quietly.

The archivist is not at his post. 
The physician chooses his words with more care than before, 
as if handling something fragile. 
The herald is careful in a way that is new to him and 
sits on him like an unfamiliar coat.

In the courtyard the prince is still. 
More still than before. 
The specific stillness of someone who has had one more thing 
removed from their world and has absorbed it into the 
place where everything else that cannot be 
changed already lives.

You add this to the notebook. You write: 
reported. consequence followed. You do not 
write what the consequence was. You do not 
need to. You know what you put in the report.
""")
        pause()

    return state


# ── DIALOGUE SYSTEM ──────────────────────────────────────────

def run_dialogue(agent_name, state):

    agent_display_names = {
        "archivist":     "THE ARCHIVIST",
        "physician":     "THE PHYSICIAN",
        "master":        "THE MASTER OF CEREMONIES",
        "herald":        "THE JUNIOR HERALD",
        "groundskeeper": "THE GROUNDSKEEPER",
        "young_asur":    "THE PRINCE",
    }

    display_name = agent_display_names.get(
        agent_name, agent_name.upper()
    )

    exchange_count = 0
    conversation_log = []  
    # Local log of this session's exchanges
    # displayed on screen, separate from 
    # the history in ollama_client

    while True:
        clear()
        header(f"SPEAKING WITH: {display_name}")
        print()

        
        if conversation_log:
            for speaker, text in conversation_log:
                divider()
                print(f" {speaker}:")
                divider()
                print()
                
                for line in text.split("\n"):
                    if line.strip():
                        print(f" {line.strip()}")
                print()

        # Input prompt
        divider()
        print(" EDMUND  [/leave]  [/notebook]")
        divider()
        print()

        player_input = input(" > ").strip()

        # Empty input — do nothing, redisplay
        if not player_input:
            continue

        # Commands
        if player_input.lower() == "/leave":
            beat = end_conversation(agent_name)
            clear()
            header(f"SPEAKING WITH: {display_name}")
            print()
            with narrative_section():
                slow_print(f" {beat}")
                interruptible_sleep(2)
            state = post_conversation_updates(
                agent_name, state
            )
            return state

        if player_input.lower() == "/notebook":
            show_notebook(state)
            continue

        # Add Edmund's line to local log
        conversation_log.append(
            ("EDMUND", player_input)
        )

        # Drift prevention
        exchange_count += 1
        if exchange_count % 5 == 0:
            inject_context_reminder(agent_name, state)

        # Young Asur trust
        if agent_name == "young_asur":
            interaction_type = evaluate_young_asur_response(
                player_input
            )
            state = evaluate_asur_interaction(
                state, interaction_type
            )

        
        clear()
        header(f"SPEAKING WITH: {display_name}")
        print()

        for speaker, text in conversation_log:
            divider()
            print(f" {speaker}:")
            divider()
            print()
            for line in text.split("\n"):
                if line.strip():
                    print(f" {line.strip()}")
            print()

        divider()
        slow_print(" ...")
        print()

        
        response = get_response(
            agent_name, player_input, state
        )

        # Add agent response to local log
        conversation_log.append(
            (display_name, response)
        )

        
        state = check_response_for_state_updates(
            agent_name, response, player_input, state
        )



def post_conversation_updates(agent_name, state):
    """
    State updates that happen when a conversation ends
    rather than during it. Returns updated state.
    """

    if agent_name == "archivist":
        state = update_archivist_stage(state)
        state = check_three_accounts(state)

    if agent_name in ["physician", "herald"]:
        state = check_three_accounts(state)

    state = check_investigation_complete(state)
    save_state(state)
    return state


def check_response_for_state_updates(
    agent_name, response, player_input, state
):
    """
    Lightweight check of agent responses to update state
    when specific information has been shared.

    This is keyword based for reliability. More
    sophisticated parsing can be added later.
    Returns updated state.
    """

    response_lower = response.lower()

    if agent_name == "groundskeeper":
        if "dust" in response_lower and \
           "disturb" in response_lower:
            state = update_state(
                state,
                "groundskeeper_confirmed_dust_disturbance",
                True
            )
        if "annotation" in response_lower or \
           "margin" in response_lower:
            state = update_state(
                state,
                "groundskeeper_confirmed_annotation_details",
                True
            )
        if "document" in response_lower and \
           "collection" in response_lower:
            state = update_state(
                state,
                "groundskeeper_confirmed_document_location",
                True
            )

    if agent_name == "physician":
        if (
            ("patient" in response_lower or "treated" in response_lower or
     "      examined" in response_lower or "medical" in response_lower)
            and
            ("reader" in response_lower or "household" in response_lower or
            "visitor" in response_lower or "guest" in response_lower)
        ):
            state = update_state(
                state,
        "physician_confirmed_reader_as_patient",
        True
    )
        if "patient" in response_lower and \
           "household" in response_lower:
            state = update_state(
                state,
                "physician_confirmed_reader_as_patient",
                True
            )
        if "match" in response_lower or \
           ("recognize" in response_lower and
                "description" in response_lower):
            state = update_state(
                state, "physician_match_triggered", True
            )

    if agent_name == "master":
        if "mourning" in response_lower and \
           ("irregular" in response_lower or
                "deviat" in response_lower):
            state = update_state(
                state,
                "master_gave_mourning_irregularities",
                True
            )
        if "departure" in response_lower and \
           "irregular" in response_lower:
            state = update_state(
                state,
                "master_gave_reader_departure_irregularity",
                True
            )
        if "corridor" in response_lower and \
           "maintenance" in response_lower and \
           "deviat" in response_lower:
            state = update_state(
                state,
                "master_checked_corridor_maintenance",
                True
            )

    if agent_name == "herald":
        if "pattern" in response_lower and \
           "changed" in response_lower:
            state = update_state(
                state, "herald_gave_pattern_changes", True
            )
        if "remember" in response_lower and \
           ("reader" in response_lower or
                "household" in response_lower):
            state = update_state(
                state, "herald_gave_reader_memory", True
            )
        if "informal" in response_lower and \
           "deliver" in response_lower:
            state = update_state(
                state, "herald_gave_informal_delivery", True
            )
        if "address" in response_lower or \
           "district" in response_lower:
            if state["herald_gave_informal_delivery"]:
                state = update_state(
                    state, "herald_gave_address", True
                )

    if agent_name == "archivist":
        if "book" in response_lower and \
           ("deliver" in response_lower or
                "traveler" in response_lower):
            state = update_state(
                state,
                "archivist_gave_book_and_traveler",
                True
            )
        if ("prince" in response_lower or
                "young" in response_lower) and \
           ("corridor" in response_lower or
                "record" in response_lower or
                "room" in response_lower):
            state = update_state(
                state,
                "archivist_gave_young_asur_shape",
                True
            )
        if "departed" in response_lower or \
           ("left" in response_lower and
                "palace" in response_lower and
                "record" in response_lower):
            state = update_state(
                state,
                "archivist_gave_departed_reader",
                True
            )
        if "map" in response_lower and \
           "older" in response_lower:
            state = update_state(
                state,
                "archivist_gave_older_maps",
                True
            )

    if agent_name == "young_asur":
        if "mother" in response_lower or \
           "her room" in response_lower:
            state = update_state(
                state,
                "young_asur_gave_mother_acknowledgment",
                True
            )
        if "deliver" in response_lower or \
           "direction" in response_lower:
            state = update_state(
                state,
                "young_asur_gave_informal_delivery_direction",
                True
            )
        if "remember" in response_lower and \
           ("reader" in response_lower or
                "felt" in response_lower or
                "room" in response_lower):
            state = update_state(
                state,
                "young_asur_gave_reader_memory",
                True
            )

    save_state(state)
    return state


# NOTEBOOK DISPLAY

def show_notebook(state):
    """Display Edmund's notebook."""
    clear()
    print(generate_notebook(state))
    pause()


# ENDING SEQUENCE

def trigger_ending(state):
    """
    The investigation is complete. 
    Edmund surfaces from the book. 
    The thread now clearly points to Veth,
    where he was all along.
    """
    clear()
    with narrative_section():
        interruptible_sleep(1)

        slow_print("")
        slow_print(" The book is lighter than it was.")
        interruptible_sleep(1.5)

        slow_print("")
        slow_print(" You did not notice when you stopped")
        slow_print(" reading and started returning.")
        interruptible_sleep(1.5)

        clear()
        interruptible_sleep(1)

        print_wrapped("""
    Your apartment. The investigation board on the walls. 
    The Eden Exit book in your lap, lighter than it was 
    when you opened it, as if something has been used 
    from it that was not ink or paper.

    You look at what you wrote down. The translated 
    address from the margin of an ancient document, 
    carried through maps of a city that no longer 
    exists in its ancient form.

    You cross reference it against your existing 
    knowledge of Veth. Against the wrongnesses you 
    catalogued when you first arrived. The streets 
    that locals reference but cannot direct you to. 
    The buildings in no civic record. The districts 
    that exist at the edges of the city's official 
    geography.

    The location corresponds.

    Not exactly. Not cleanly. But with the specific 
    correspondence your mind has been trained to 
    recognize across this entire investigation. One 
    of Veth's unrecorded districts. A place that 
    exists on no official map but is obviously old 
    and heavily used. A place you noticed and filed 
    as wrong without knowing why.

    You have a direction. 
    A place in your own city that a marginal annotation 
    in an ancient document points at, through a chain 
    of reasoning that no sane investigator would trust.

    You won't allow yourself to ever stop trusting it.
    """)

        interruptible_sleep(2)
        print()
        divider()

        # Show final rose notation
        slow_print(" You open your notebook.")
        interruptible_sleep(1)
        slow_print(" You add one line at the bottom.")
        interruptible_sleep(1)
        slow_print("")
        slow_print("   The unrecorded district.")
        slow_print("   Something red in the corner")
        slow_print("   of the window across the street.")
        slow_print("   Has been there since you returned.")
        slow_print("   You did not notice it before today.")
        interruptible_sleep(2)
        print()
        slow_print(" You noticed it before today.")
        interruptible_sleep(3)

        print()
        divider()
        print()
        slow_print(" The thread continues.")
        interruptible_sleep(2)
        print()
        slow_print(" [End of demo]")
        print()

    state = update_state(state, "investigation_complete", True)
    save_state(state)

    input()
    return state

# MAIN ENTRY POINT

def new_game():
    """Initialize a new game."""
    from state import DEFAULT_STATE
    import copy

    state = copy.deepcopy(DEFAULT_STATE)
    save_state(state)
    reset_all_conversations()
    return state


def title_screen():
    """Display title screen and main menu."""
    clear()
    print()
    print(" " + "═" * (WIDTH - 2))
    print()
    with narrative_section():
        slow_print("         B L O O D   R O S E")
        print()
        slow_print("    a detective horror game — demo")
        print()
        print(" " + "═" * (WIDTH - 2))
        print()
        interruptible_sleep(0.5)

    save_exists = os.path.exists("save_state.json")

    print(" [1] New investigation")
    if save_exists:
        print(" [2] Continue")
    print(" [Q] Quit")
    print()

    while True:
        choice = input(" > ").strip().upper()

        if choice == "1":
            return new_game()
        elif choice == "2" and save_exists:
            return load_state()
        elif choice == "Q":
            sys.exit()
        else:
            slow_print(" Choose an available option.")


def opening_sequence(state):
    """
    The transition into the book world.
    Shown once at the start of a new game.
    """
    if state.get("opening_shown"):
        return state

    clear()
    with narrative_section():
        interruptible_sleep(1)

        print_wrapped("""
The book has been in your possession for eleven days. 
You have opened it six times by now. 
Each time you have read further than the time before.

Tonight you open it and do not stop.
""")
        interruptible_sleep(2)

        print_wrapped("""
The world it describes is specific in ways that 
fiction is not specific. The architecture is wrong 
for invention, too internally consistent, too 
physically coherent, the kind of detail that 
accumulates from observation rather than imagination.

You are aware at some point that you have stopped 
reading and started perceiving.
""")
        interruptible_sleep(2)

        print_wrapped("""
You are in the palace. 
You do not know how you arrived. 
You know what you are here for in the 
way you always know what you are here for 
someone who has left wrongness in the available 
evidence and wrongness requires following.

A functionary is waiting to receive you in the 
reception hall. You have been expected, apparently, 
though you cannot say by whom.

So the story simply begins.
""")

    state = update_state(state, "opening_shown", True)
    pause()
    return state


def main():
    """Main entry point."""
    state = title_screen()

    # Show opening sequence for new games
    if not state.get("opening_shown"):
        state = opening_sequence(state)

    # Handle dialogue from navigation
    # Patch navigate to use run_dialogue
    # This connects the S action in navigation
    # to the dialogue system

    original_navigate = navigate

    def navigate_with_dialogue(state):
        """
        Extended navigate that intercepts S actions
        and routes them to run_dialogue.
        """
        current_location = "reception_hall"

        while True:
            clear()
            header(
                LOCATION_NAMES[current_location].upper()
            )

            description = get_location_description(
                current_location, state
            )
            print()
            print_wrapped(description)

            state = mark_location_visited(
                state, current_location
            )
            state = handle_location_logic(
                current_location, state
            )
            state = check_investigation_complete(state)

            if state["investigation_complete"]:
                state = trigger_ending(state)
                return state

            print()
            divider()
            print(" WHAT NOW")
            divider()

            actions = get_location_actions(
                current_location, state
            )
            for key, desc in actions.items():
                print(f" [{key}] {desc}")

            print()
            nav_options = show_navigation_menu(
                current_location, state
            )

            choice = input("\n> ").strip().upper()

            if choice == "Q":
                save_state(state)
                print()
                slow_print(" Progress saved. Edmund waits.")
                interruptible_sleep(1)
                sys.exit()

            elif choice == "N":
                show_notebook(state)

            elif choice == "S" and "S" in actions:
                # Route to dialogue
                agent = AGENT_FOR_LOCATION.get(
                    current_location
                )
                if agent:
                    state = run_dialogue(agent, state)

            elif choice in actions:
                state = handle_action(
                    choice, current_location, state
                )

            else:
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(nav_options):
                        current_location = nav_options[idx]
                    else:
                        slow_print(
                            " That option is not available."
                        )
                        interruptible_sleep(0.8)
                except ValueError:
                    slow_print(
                        " Edmund considers this. "
                        "Nothing happens."
                    )
                    interruptible_sleep(0.8)

    navigate_with_dialogue(state)


if __name__ == "__main__":
    main()