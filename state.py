# state.py
import json
import os

SAVE_FILE = "save_state.json"

DEFAULT_STATE = {

    # ── INVESTIGATION KNOWLEDGE ──────────────────────────────
    "edmund_has_authentication_task": False,
    "edmund_found_gap_in_document": False,
    "edmund_found_marginal_annotation": False,
    "edmund_has_older_maps": False,
    "edmund_has_translated_address": False,

    # ── GROUNDSKEEPER ────────────────────────────────────────
    "spoke_to_groundskeeper": False,
    "groundskeeper_confirmed_dust_disturbance": False,
    "groundskeeper_confirmed_document_location": False,
    "groundskeeper_confirmed_annotation_details": False,

    # ── PHYSICIAN ────────────────────────────────────────────
    "spoke_to_physician": False,
    "physician_gave_official_account": False,
    "physician_confirmed_reader_as_patient": False,
    "physician_match_triggered": False,

    # ── MASTER OF CEREMONIES ─────────────────────────────────
    "spoke_to_master": False,
    "master_gave_mourning_irregularities": False,
    "master_gave_reader_departure_irregularity": False,
    "master_checked_corridor_maintenance": False,

    # ── JUNIOR HERALD ────────────────────────────────────────
    "spoke_to_herald": False,
    "herald_gave_pattern_changes": False,
    "herald_gave_reader_memory": False,
    "herald_gave_informal_delivery": False,
    "herald_gave_address": False,

    # ── ARCHIVIST ────────────────────────────────────────────
    "spoke_to_archivist": False,
    "archivist_stage": 1,
    "archivist_gave_book_and_traveler": False,
    "archivist_gave_young_asur_shape": False,
    "archivist_gave_departed_reader": False,
    "archivist_gave_older_maps": False,

    # ── YOUNG ASUR ───────────────────────────────────────────
    "spoke_to_young_asur": False,
    "young_asur_trust_level": 0,
    "young_asur_interactions": 0,
    "young_asur_gave_palace_observations": False,
    "young_asur_gave_mother_acknowledgment": False,
    "young_asur_gave_informal_delivery_direction": False,
    "young_asur_gave_reader_memory": False,

    # ── QUEEN'S ROOM ─────────────────────────────────────────
    "queen_room_accessible": False,
    "edmund_entered_queens_room": False,
    "edmund_found_mementos": False,
    "edmund_found_record": False,
    "player_reported_to_king": False,
    "punishment_consequence_triggered": False,

    # ── BLOOD ROSES NOTICED ──────────────────────────────────
    "roses_noticed": [],

    # ── FINAL THREAD ─────────────────────────────────────────
    "three_accounts_of_reader_assembled": False,
    "marginal_address_cross_referenced": False,
    "veth_district_identified": False,
    "investigation_complete": False,

    # ── LOCATION VISIT TRACKING ──────────────────────────────
    "visited_locations": []
}


def load_state():
    """Load state from save file or return default if none exists."""
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r") as f:
            return json.load(f)
    return DEFAULT_STATE.copy()


def save_state(state):
    """Write current state to save file."""
    with open(SAVE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def update_state(state, key, value):
    """Update a single state variable and save."""
    state[key] = value
    save_state(state)
    return state


def notice_rose(state, location):
    """Add a blood rose sighting to the noticed list."""
    if location not in state["roses_noticed"]:
        state["roses_noticed"].append(location)
        save_state(state)
    return state


def mark_location_visited(state, location):
    """Record that a location has been visited."""
    if location not in state["visited_locations"]:
        state["visited_locations"].append(location)
        save_state(state)
    return state


def is_first_visit(state, location):
    """Check if this is the player's first visit to a location."""
    return location not in state["visited_locations"]


# ── PROGRESSION GATE CHECKERS ────────────────────────────────

def can_access_queens_room(state):
    """Queen's room unlocks when archivist reaches stage 3."""
    return state["archivist_stage"] >= 3


def can_access_sealed_corridor(state):
    """Sealed corridor unlocks with queen's room."""
    return can_access_queens_room(state)


def archivist_can_advance_to_stage_2(state):
    """
    Stage 2 unlocks when Edmund demonstrates specific prior
    knowledge — finding the gap in the document or the
    annotation is sufficient.
    """
    return (
        state["edmund_found_gap_in_document"] or
        state["edmund_found_marginal_annotation"]
    )


def archivist_can_advance_to_stage_3(state):
    """
    Stage 3 unlocks when Edmund references the dust
    disturbance — requires groundskeeper contact first.
    """
    return state["groundskeeper_confirmed_dust_disturbance"]


def archivist_can_advance_to_stage_4(state):
    """
    Stage 4 — the negotiation — requires Edmund to have
    established knowledge of young Asur and the room.
    This means stage 3 must be complete and the queen's
    room must have been entered.
    """
    return (
        state["archivist_stage"] >= 3 and
        state["edmund_entered_queens_room"]
    )


def archivist_maps_available(state):
    """Older maps only available after stage 4 complete."""
    return state["archivist_gave_departed_reader"]


def herald_can_give_address(state):
    """
    Address only available after Edmund has established
    that informal channels exist — requires the informal
    delivery to have been discussed first.
    """
    return state["herald_gave_informal_delivery"]


def master_can_check_corridor(state):
    """
    Master checks corridor maintenance only after Edmund
    has gathered enough from groundskeeper and archivist
    to know what he is looking for.
    """
    return (
        state["groundskeeper_confirmed_dust_disturbance"] and
        state["archivist_stage"] >= 2
    )


def three_accounts_assembled(state):
    """
    Three independent accounts of the reader assembled
    when physician, herald, and archivist have all
    contributed their piece.
    """
    return (
        state["physician_confirmed_reader_as_patient"] and
        state["herald_gave_reader_memory"] and
        state["archivist_gave_departed_reader"]
    )


def investigation_can_complete(state):
    """
    Final resolution available when address is translated
    and cross referenced against Veth geography.
    """
    return (
        state["archivist_gave_older_maps"] and
        state["edmund_has_translated_address"] and
        state["three_accounts_of_reader_assembled"]
    )


# ── YOUNG ASUR TRUST MANAGEMENT ──────────────────────────────

def evaluate_asur_interaction(state, interaction_type):
    """
    Update young Asur's trust level based on interaction
    quality. Call this after each conversation with him.

    interaction_type options:
    "genuine"       — Edmund treated him as person worth
                      hearing, patient, not instrumental
    "formal"        — Edmund was formal or transactional,
                      no trust change
    "approached_archivist" — Edmund approached forbidden
                      territory, trust resets to 0
    """
    if interaction_type == "genuine":
        state["young_asur_interactions"] += 1
        # Trust increases at interaction thresholds
        interactions = state["young_asur_interactions"]
        if interactions >= 1:
            state["young_asur_trust_level"] = max(
                state["young_asur_trust_level"], 1
            )
        if interactions >= 3:
            state["young_asur_trust_level"] = max(
                state["young_asur_trust_level"], 2
            )
        if interactions >= 5:
            state["young_asur_trust_level"] = 3

    elif interaction_type == "approached_archivist":
        state["young_asur_trust_level"] = 0
        state["young_asur_interactions"] = 0

    # "formal" changes nothing

    save_state(state)
    return state


def update_archivist_stage(state):
    current = state["archivist_stage"]
    previous = current

    if current == 1 and archivist_can_advance_to_stage_2(state):
        state["archivist_stage"] = 2
    elif current == 2 and archivist_can_advance_to_stage_3(state):
        state["archivist_stage"] = 3
        state["queen_room_accessible"] = True
    elif current == 3 and archivist_can_advance_to_stage_4(state):
        state["archivist_stage"] = 4

    # If stage advanced, reset conversation history
    # so the new injection takes effect cleanly
    if state["archivist_stage"] != previous:
        from ollama_client import reset_conversation
        reset_conversation("archivist")

    save_state(state)
    return state


def check_three_accounts(state):
    """Check and update three accounts assembled flag."""
    if three_accounts_assembled(state):
        state["three_accounts_of_reader_assembled"] = True
        save_state(state)
    return state


def check_investigation_complete(state):
    """Check and update investigation complete flag."""
    if investigation_can_complete(state):
        state["investigation_complete"] = True
        save_state(state)
    return state


def trigger_punishment_consequence(state):
    """
    Called when player reports findings to the king.
    Sets consequences in motion.
    """
    state["player_reported_to_king"] = True
    state["punishment_consequence_triggered"] = True
    # Archivist disappears from post after this
    # Young Asur becomes more still
    # Both reflected in their changed state descriptions
    save_state(state)
    return state