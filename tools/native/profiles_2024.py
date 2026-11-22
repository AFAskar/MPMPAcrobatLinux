"""Shared 2024 MPMB comprehensive character/workflow profiles for Native and Reader parity.

Covers all previously-unqualified 2024 core classes (Cleric, Druid, Paladin,
Ranger, Rogue, Sorcerer, Warlock, Wizard), Multiclassing (Paladin/Warlock +
Fighter/Wizard), 2024 Species, 2024 Backgrounds & Origin Feats, 2024 Weapon
Mastery, genuine class feature choices, resource spending & short/long rests,
Spell Sheet generation, Wild Shape,
Companion pages, and cold save/reopen verification.
"""

CONSOLE_SENTINEL = "MPMB 2024 comprehensive class workflow console sentinel"

# Helper JS snippet to spend a named Limited Feature dynamically by scanning actual rows.
def spend_resource_js(prefix, amount):
    import json
    return (
        "(function(){"
        "for(var i=0;i<numFields;i++){"
        "var n=getNthFieldName(i),m=/^Limited Feature (\\d+)$/.exec(n);"
        f"if(m&&getField(n).valueAsString.indexOf({json.dumps(prefix)})===0){{"
        f"getField('Limited Feature Used '+m[1]).value={json.dumps(str(amount))};return;"
        "}"
        "}"
        f"throw Error('Missing resource: '+{json.dumps(prefix)});"
        "})()"
    )


def _stats(str_, dex, con, int_, wis, cha):
    return [
        ("edit", "Str", str(str_)),
        ("edit", "Dex", str(dex)),
        ("edit", "Con", str(con)),
        ("edit", "Int", str(int_)),
        ("edit", "Wis", str(wis)),
        ("edit", "Cha", str(cha)),
    ]


# Each profile defines:
#   batch: 'A' (local Reader VM) or 'B' (cloud cloud-lab Reader VM)
#   description: concise scope
#   phases: list of (label, ops, check_fn_name)
#     where ops are tuples:
#       ('edit', field, value)
#       ('cmd', original_mpmb_js_command)
#       ('eval', js_expression)  # only for dynamic resource row lookup in native/reader
#   cold_reopen_phase: label of the final phase to cold-reopen & verify
#   mixed_followup: (label, ops) executed AFTER cold reopen in mixed-engine qualification
PROFILES = {
    "cleric": {
        "batch": "A",
        "description": "2024 Life Cleric + Dwarf + Acolyte + Divine Order (Protector) + Blessed Strikes (Divine Strike) + Channel Divinity spend/rest + Spell Sheet",
        "phases": [
            (
                "cleric-l1-setup",
                _stats(14, 10, 14, 10, 16, 12)
                + [
                    ("edit", "Race", "Dwarf"),
                    ("edit", "Background", "Acolyte"),
                    ("cmd", "ApplyClasses('Cleric 1', false)"),
                    ("cmd", "ClassFeatureOptions(['cleric', 'divine order', 'protector', false, 'add'])"),
                    ("edit", "Attack.1.Weapon Selection", "Mace"),
                ],
            ),
            (
                "cleric-l7-life-blessed-spells",
                [
                    ("cmd", "ApplyClasses('Cleric (Life Domain) 7', false)"),
                    ("cmd", "ClassFeatureOptions(['cleric', 'blessed strikes', 'divine strike', false, 'add'])"),
                    ("cmd", "GenerateSpellSheetWithAll(false, true)"),
                ],
            ),
            (
                "cleric-l7-spend-rest",
                [
                    ("eval", spend_resource_js("Channel Divinity", 2)),
                    ("cmd", "resetLimFeaUsed('short rest')"),
                ],
            ),
            (
                "cleric-l14-progress",
                [
                    ("cmd", "ApplyClasses('Cleric (Life Domain) 14', false)"),
                    ("cmd", "ClassFeatureOptions(['cleric', 'improved blessed strikes', 'divine strike', false, 'add'])"),
                ],
            ),
            (
                "cleric-l5-down",
                [
                    ("cmd", "ApplyClasses('Cleric (Life Domain) 5', false)"),
                ],
            ),
        ],
        "mixed_followup": (
            "cleric-l9-mixed",
            [
                ("cmd", "ApplyClasses('Cleric (Life Domain) 9', false)"),
            ],
        ),
    },
    "druid": {
        "batch": "A",
        "description": "2024 Land Druid + Elf + Primal Order (Magician) + Land Type (Temperate->Arid) + Wild Shape + Spell Sheet",
        "phases": [
            (
                "druid-l3-land-temperate",
                _stats(10, 14, 14, 12, 16, 10)
                + [
                    ("edit", "Race", "Wood Elf"),
                    ("cmd", "ApplyClasses('Druid (Circle of the Land) 3', false)"),
                    ("cmd", "ClassFeatureOptions(['druid', 'primal order', 'magician', false, 'add'])"),
                    ("cmd", "ClassFeatureOptions(['druid', 'subclassfeature3', 'temperate', false, 'add'])"),
                ],
            ),
            (
                "druid-l7-wildshape-spells",
                [
                    ("cmd", "ApplyClasses('Druid (Circle of the Land) 7', false)"),
                    ("cmd", "ClassFeatureOptions(['druid', 'elemental fury', 'primal strike', false, 'add'])"),
                    ("cmd", "ClassFeatureOptions(['druid', 'subclassfeature3', 'arid', false, 'add'])"),
                    ("cmd", "DoTemplate('WSfront', 'Add', null, true)"),
                    ("edit", "P6.WSfront.Wildshape.Race.1", "wolf"),
                    ("cmd", "GenerateSpellSheetWithAll(false, true)"),
                ],
            ),
            (
                "druid-l7-spend-rest",
                [
                    ("eval", spend_resource_js("Wild Shape", 2)),
                    ("cmd", "resetLimFeaUsed('long rest')"),
                ],
            ),
        ],
        "mixed_followup": (
            "druid-l10-mixed",
            [
                ("cmd", "ApplyClasses('Druid (Circle of the Land) 10', false)"),
            ],
        ),
    },
    "paladin": {
        "batch": "A",
        "description": "2024 Devotion Paladin + Dragonborn + Soldier + Weapon Mastery + Fighting Style (Defense) + Lay on Hands / Aura of Protection + Spell Sheet",
        "phases": [
            (
                "paladin-l2-setup",
                _stats(16, 10, 14, 10, 12, 16)
                + [
                    ("edit", "Race", "Gold Dragonborn"),
                    ("edit", "Background", "Soldier"),
                    ("cmd", "ApplyClasses('Paladin 2', false)"),
                    ("edit", "Attack.1.Weapon Selection", "Longsword"),
                    ("edit", "Attack.2.Weapon Selection", "Javelin"),
                ],
            ),
            (
                "paladin-l6-devotion-aura-spells",
                [
                    ("cmd", "ApplyClasses('Paladin (Oath of Devotion) 6', false)"),
                    ("edit", "Feat Name 1", "Defense"),
                    ("cmd", "GenerateSpellSheetWithAll(false, true)"),
                ],
            ),
            (
                "paladin-l6-spend-rest",
                [
                    ("eval", spend_resource_js("Lay on Hands", 15)),
                    ("eval", spend_resource_js("Channel Divinity", 1)),
                    ("cmd", "resetLimFeaUsed('short rest')"),
                ],
            ),
        ],
        "mixed_followup": (
            "paladin-l11-mixed",
            [
                ("cmd", "ApplyClasses('Paladin (Oath of Devotion) 11', false)"),
                ("cmd", "resetLimFeaUsed('long rest')"),
            ],
        ),
    },
    "ranger": {
        "batch": "A",
        "description": "2024 Hunter Ranger + High Elf + Fighting Style (Archery) + Companion Page (Timber Wolf) + Spell Sheet",
        "phases": [
            (
                "ranger-l3-hunter",
                _stats(12, 16, 14, 10, 16, 10)
                + [
                    ("edit", "Race", "High Elf"),
                    ("cmd", "ApplyClasses('Ranger (Hunter) 3', false)"),
                    ("edit", "Feat Name 1", "Archery"),
                    ("edit", "Attack.1.Weapon Selection", "Longbow"),
                ],
            ),
            (
                "ranger-l5-companion-spells",
                [
                    ("cmd", "ApplyClasses('Ranger (Hunter) 5', false)"),
                    ("cmd", "DoTemplate('AScomp', 'Add', null, true)"),
                    ("edit", "P5.AScomp.Comp.Race", "Wolf"),
                    ("edit", "P5.AScomp.Comp.Desc.Name", "Timber"),
                    ("cmd", "GenerateSpellSheetWithAll(false, true)"),
                ],
            ),
            (
                "ranger-l5-spend-rest",
                [
                    ("eval", spend_resource_js("Favored Enemy", 2)),
                    ("cmd", "resetLimFeaUsed('long rest')"),
                ],
            ),
        ],
        "mixed_followup": (
            "ranger-l9-mixed",
            [
                ("cmd", "ApplyClasses('Ranger (Hunter) 9', false)"),
            ],
        ),
    },
    "rogue": {
        "batch": "B",
        "description": "2024 Thief Rogue + Halfling + Criminal (Alert) + Sneak Attack scaling L1/5/11/20 + Weapon Mastery (Dagger/Shortbow) + Cunning Strike",
        "phases": [
            (
                "rogue-l1-criminal",
                _stats(10, 16, 14, 12, 12, 14)
                + [
                    ("edit", "Race", "Halfling"),
                    ("edit", "Background", "Criminal"),
                    ("cmd", "ApplyClasses('Rogue 1', false)"),
                    ("edit", "Attack.1.Weapon Selection", "Dagger"),
                    ("edit", "Attack.2.Weapon Selection", "Shortbow"),
                ],
            ),
            (
                "rogue-l5-thief-cunning",
                [
                    ("cmd", "ApplyClasses('Rogue (Thief) 5', false)"),
                ],
            ),
            (
                "rogue-l11-reliable",
                [
                    ("cmd", "ApplyClasses('Rogue (Thief) 11', false)"),
                ],
            ),
            (
                "rogue-l20-capstone",
                [
                    ("cmd", "ApplyClasses('Rogue (Thief) 20', false)"),
                ],
            ),
        ],
        "mixed_followup": (
            "rogue-l7-mixed",
            [
                ("cmd", "ApplyClasses('Rogue (Thief) 7', false)"),
            ],
        ),
    },
    "sorcerer": {
        "batch": "B",
        "description": "2024 Draconic Sorcerer + Tiefling + Metamagic (Quickened/Subtle) + Draconic Resilience AC/HP + Innate Sorcery / Sorcery Points spend/rest + Spell Sheet",
        "dialogs": [
            {"title": "SOURCE SELECTION DIALOG", "result": "ok"},
            {"title": "ASK USER DIALOG", "header": "Select Species Variant", "values": {"r000": True}, "result": "ok"},
            {"title": "ASK USER DIALOG", "header": "Select Size Category for Tiefling", "values": {"r000": True}, "result": "ok"},
            {"title": "ASK USER DIALOG", "header": "Select proficiencies", "result": "ok"},
            {"title": "ASK USER DIALOG", "header": "Select Spellcasting Ability for Abyssal Tiefling", "values": {"r000": True}, "result": "ok"},
        ],
        "phases": [
            (
                "sorcerer-l3-draconic",
                _stats(8, 14, 14, 10, 12, 18)
                + [
                    ("edit", "Race", "Tiefling"),
                    ("cmd", "ApplyClasses('Sorcerer (Draconic Sorcery) 3', false)"),
                    ("cmd", "ClassFeatureOptions(['sorcerer', 'metamagic', 'quickened spell', true, 'add'])"),
                    ("cmd", "ClassFeatureOptions(['sorcerer', 'metamagic', 'subtle spell', true, 'add'])"),
                ],
            ),
            (
                "sorcerer-l6-spells",
                [
                    ("cmd", "ApplyClasses('Sorcerer (Draconic Sorcery) 6', false)"),
                    ("cmd", "GenerateSpellSheetWithAll(false, true)"),
                ],
            ),
            (
                "sorcerer-l6-spend-rest",
                [
                    ("eval", spend_resource_js("Sorcery Points", 4)),
                    ("eval", spend_resource_js("Innate Sorcery", 1)),
                    ("cmd", "resetLimFeaUsed('long rest')"),
                ],
            ),
        ],
        "mixed_followup": (
            "sorcerer-l10-mixed",
            [
                ("cmd", "ApplyClasses('Sorcerer (Draconic Sorcery) 10', false)"),
            ],
        ),
    },
    "warlock": {
        "batch": "B",
        "description": "2024 Fiend Warlock + Human + Tough Feat + Eldritch Invocations (Devil's Sight / Armor of Shadows) + Pact Magic progression L1/5/11/17 + rests + Spell Sheet",
        "dialogs": [
            {"title": "SOURCE SELECTION DIALOG", "result": "ok"},
            {"title": "ASK USER DIALOG", "header": "Select Size Category for Human", "values": {"r000": True}, "result": "ok"},
            {"title": "ASK USER DIALOG", "header": "Select proficiencies", "result": "ok"},
            {"title": "ASK USER DIALOG", "header": "Select Origin Feat", "values": {"r000": True}, "result": "ok"},
        ],
        "phases": [
            (
                "warlock-l3-fiend",
                _stats(10, 14, 14, 12, 10, 18)
                + [
                    ("edit", "Race", "Human"),
                    ("edit", "Feat Name 1", "Tough"),
                    ("cmd", "ApplyClasses('Warlock (Fiend Patron) 3', false)"),
                    ("cmd", "ClassFeatureOptions(['warlock', 'eldritch invocations', \"devil's sight\", true, 'add'])"),
                    ("cmd", "ClassFeatureOptions(['warlock', 'eldritch invocations', 'armor of shadows', true, 'add'])"),
                ],
            ),
            (
                "warlock-l11-pact-spells",
                [
                    ("cmd", "ApplyClasses('Warlock (Fiend Patron) 11', false)"),
                    ("cmd", "GenerateSpellSheetWithAll(false, true)"),
                ],
            ),
            (
                "warlock-l11-spend-rest",
                [
                    ("eval", spend_resource_js("Magical Cunning", 1)),
                    ("cmd", "resetLimFeaUsed('long rest')"),
                ],
            ),
            (
                "warlock-l17-arcanum",
                [
                    ("cmd", "ApplyClasses('Warlock (Fiend Patron) 17', false)"),
                ],
            ),
        ],
        "mixed_followup": (
            "warlock-l5-mixed",
            [
                ("cmd", "ApplyClasses('Warlock (Fiend Patron) 5', false)"),
            ],
        ),
    },
    "wizard": {
        "batch": "B",
        "description": "2024 Evoker Wizard + Gnome + Sage + Scholar (Arcana Expertise) + Arcane Recovery spend/rest + Spell Sheet",
        "dialogs": [
            {"title": "SOURCE SELECTION DIALOG", "result": "ok"},
            {"title": "ASK USER DIALOG", "header": "Select proficiencies", "result": "ok"},
            {"title": "ASK USER DIALOG", "header": "Select Spellcasting Ability for Forest Gnome", "values": {"r000": True}, "result": "ok"},
            {"title": "ASK USER DIALOG", "header": "Select Spellcasting Ability for Magic Initiate [Wizard] (feat)", "values": {"r000": True}, "result": "ok"},
        ],
        "phases": [
            (
                "wizard-l3-evoker",
                _stats(8, 14, 14, 18, 12, 10)
                + [
                    ("edit", "Race", "Forest Gnome"),
                    ("edit", "Background", "Sage"),
                    ("cmd", "ApplyClasses('Wizard (Evoker) 3', false)"),
                    ("cmd", "ClassFeatureOptions(['wizard', 'scholar', 'arcana expertise', false, 'add'])"),
                ],
            ),
            (
                "wizard-l10-empowered-spells",
                [
                    ("cmd", "ApplyClasses('Wizard (Evoker) 10', false)"),
                    ("cmd", "GenerateSpellSheetWithAll(false, true)"),
                ],
            ),
            (
                "wizard-l10-spend-rest",
                [
                    ("eval", spend_resource_js("Arcane Recovery", 1)),
                    ("cmd", "resetLimFeaUsed('long rest')"),
                ],
            ),
        ],
        "mixed_followup": (
            "wizard-l6-mixed",
            [
                ("cmd", "ApplyClasses('Wizard (Evoker) 6', false)"),
            ],
        ),
    },
    "multiclass": {
        "batch": "B",
        "description": "2024 Multiclass Paladin (Devotion) 6 / Warlock (Fiend) 3 + Dual Hit Dice + Pact Magic & Spellcasting Slots + Aura of Protection + Tough + Multi-caster Spell Sheet",
        "dialogs": [
            {"title": "SOURCE SELECTION DIALOG", "result": "ok"},
            {"title": "ASK USER DIALOG", "header": "Select Size Category for Human", "values": {"r000": True}, "result": "ok"},
            {"title": "ASK USER DIALOG", "header": "Select proficiencies", "result": "ok"},
            {"title": "ASK USER DIALOG", "header": "Select Origin Feat", "values": {"r000": True}, "result": "ok"},
        ],
        "phases": [
            (
                "mc-pal6-war3",
                _stats(16, 10, 14, 10, 12, 18)
                + [
                    ("edit", "Race", "Human"),
                    ("edit", "Feat Name 1", "Tough"),
                    ("cmd", "ApplyClasses('Paladin (Oath of Devotion) 6, Warlock (Fiend Patron) 3', false)"),
                    ("edit", "Attack.1.Weapon Selection", "Longsword"),
                    ("cmd", "GenerateSpellSheetWithAll(false, true)"),
                ],
            ),
            (
                "mc-pal6-war3-rests",
                [
                    ("eval", spend_resource_js("Lay on Hands", 20)),
                    ("eval", spend_resource_js("Channel Divinity", 1)),
                    ("cmd", "resetLimFeaUsed('short rest')"),
                ],
            ),
            (
                "mc-ftr3-wiz5",
                [
                    ("cmd", "ApplyClasses('Fighter (Champion) 3, Wizard (Evoker) 5', false)"),
                    ("cmd", "ClassFeatureOptions(['wizard', 'scholar', 'arcana expertise', false, 'add'])"),
                    ("cmd", "GenerateSpellSheetWithAll(false, true)"),
                ],
            ),
        ],
        "mixed_followup": (
            "mc-ftr5-wiz5-mixed",
            [
                ("cmd", "ApplyClasses('Fighter (Champion) 5, Wizard (Evoker) 5', false)"),
            ],
        ),
    },
}


def validate_profile_state(profile_name, phase_label, state):
    """Verify concrete functional invariants for each 2024 profile phase."""
    assert not state["errors"], (profile_name, phase_label, state["errors"])
    assert not state["unavailable"], (profile_name, phase_label, state["unavailable"])
    assert state["calculation"] == {"app": True, "doc": True, "delay": False}, (
        profile_name,
        phase_label,
        state["calculation"],
    )
    f = state["fields"]
    rows = {r["name"]: r for r in state["rows"]}

    def find_row(prefix):
        matches = [r for k, r in rows.items() if k.startswith(prefix)]
        assert matches, (profile_name, phase_label, f"Missing row starting with {prefix}", list(rows))
        return matches[0]

    if profile_name == "cleric":
        if phase_label == "cleric-l1-setup":
            assert f["Character Level"] == "1" and f["Proficiency Bonus"] == "2"
            assert state["identity"]["cleric"]["level"] == 1
            assert state["choices"]["classes"]["cleric"]["divine order"]["choice"] == "protector"
            assert state["race"]["known"] == "dwarf"
            assert state["background"]["known"] == "acolyte"
        elif phase_label == "cleric-l7-life-blessed-spells":
            assert f["Character Level"] == "7" and f["Proficiency Bonus"] == "3"
            assert state["identity"]["cleric"] == {"level": 7, "subclass": "cleric-life"}
            assert state["choices"]["classes"]["cleric"]["blessed strikes"]["choice"] == "divine strike"
            assert "cleric" in state["spells"]
            assert state["pages"] > 6, "Spell Sheet pages must be generated"
        elif phase_label == "cleric-l7-spend-rest":
            cd = find_row("Channel Divinity")
            # 2024 Cleric regains 1 use of Channel Divinity on short rest (or full reset depending on recovery tag)
            assert cd["used"] in ("", "0", "1"), (phase_label, cd)
        elif phase_label == "cleric-l14-progress":
            assert f["Character Level"] == "14" and f["Proficiency Bonus"] == "5"
        elif phase_label == "cleric-l5-down":
            assert f["Character Level"] == "5" and f["Proficiency Bonus"] == "3"
        elif phase_label == "cleric-l9-mixed":
            assert f["Character Level"] == "9" and f["Proficiency Bonus"] == "4"

    elif profile_name == "druid":
        if phase_label == "druid-l3-land-temperate":
            assert f["Character Level"] == "3"
            assert state["identity"]["druid"] == {"level": 3, "subclass": "druid-land"}
            assert state["choices"]["classes"]["druid"]["primal order"]["choice"] == "magician"
            assert state["choices"]["classes"]["druid"]["subclassfeature3"]["choice"] == "temperate"
        elif phase_label == "druid-l7-wildshape-spells":
            assert f["Character Level"] == "7"
            assert state["choices"]["classes"]["druid"]["subclassfeature3"]["choice"] == "arid"
            ws_race = next((v for k, v in state["notesAndActions"].items() if k.endswith("Wildshape.Race.1")), "")
            ws_str = next((v for k, v in state["notesAndActions"].items() if k.endswith("Wildshape.1.Ability.Str.Score")), "")
            assert ws_race.lower() == "wolf", state["notesAndActions"]
            assert ws_str == "14", ("2024 Wolf Str expected 14", ws_str)
            assert "druid" in state["spells"]
            assert state["pages"] > 7
        elif phase_label == "druid-l7-spend-rest":
            ws = find_row("Wild Shape")
            assert ws["used"] in ("", "0"), ws
        elif phase_label == "druid-l10-mixed":
            assert f["Character Level"] == "10" and f["Proficiency Bonus"] == "4"

    elif profile_name == "paladin":
        if phase_label == "paladin-l2-setup":
            assert f["Character Level"] == "2"
            assert state["race"]["known"].startswith("dragonborn")
            assert state["background"]["known"] == "soldier"
            assert "longsword" in f["Attack.1.Weapon Selection"].lower()
        elif phase_label == "paladin-l6-devotion-aura-spells":
            assert f["Character Level"] == "6"
            assert state["identity"]["paladin"] == {"level": 6, "subclass": "paladin-devotion"}
            # Aura of Protection adds Cha mod (+3) to all saving throws!
            assert int(f["Dex ST Mod"]) >= 3, ("Aura of Protection missing on Dex ST", f["Dex ST Mod"])
            assert "paladin" in state["spells"]
            assert state["pages"] > 6
        elif phase_label == "paladin-l6-spend-rest":
            loh = find_row("Lay on Hands")
            assert loh["used"] == "15", ("Short rest must NOT reset Long-Rest Lay on Hands", loh)
        elif phase_label == "paladin-l11-mixed":
            assert f["Character Level"] == "11" and f["Proficiency Bonus"] == "4"
            loh = find_row("Lay on Hands")
            assert loh["used"] in ("", "0"), ("Long rest must reset Lay on Hands", loh)

    elif profile_name == "ranger":
        if phase_label == "ranger-l3-hunter":
            assert f["Character Level"] == "3"
            assert state["identity"]["ranger"] == {"level": 3, "subclass": "ranger-hunter"}
            assert "elf" in state["race"]["known"]
            assert "longbow" in f["Attack.1.Weapon Selection"].lower()
        elif phase_label == "ranger-l5-companion-spells":
            assert f["Character Level"] == "5"
            comp_name = next((v for k, v in state["notesAndActions"].items() if k.endswith("Comp.Desc.Name")), "")
            comp_race = next((v for k, v in state["notesAndActions"].items() if k.endswith("Comp.Race")), "")
            comp_ac = next((v for k, v in state["notesAndActions"].items() if k.endswith("Comp.Use.AC")), "")
            assert comp_name == "Timber" and "wolf" in comp_race.lower() and comp_ac != "", state["notesAndActions"]
            assert "ranger" in state["spells"]
            assert state["pages"] > 7
        elif phase_label == "ranger-l5-spend-rest":
            fe = find_row("Favored Enemy")
            assert fe["used"] in ("", "0"), fe
        elif phase_label == "ranger-l9-mixed":
            assert f["Character Level"] == "9" and f["Proficiency Bonus"] == "4"

    elif profile_name == "rogue":
        if phase_label == "rogue-l1-criminal":
            assert f["Character Level"] == "1"
            assert state["race"]["known"].startswith("halfling")
            assert state["background"]["known"] == "criminal"
        elif phase_label == "rogue-l5-thief-cunning":
            assert f["Character Level"] == "5"
            assert state["identity"]["rogue"] == {"level": 5, "subclass": "rogue-thief"}
            assert "3d6" in state["notesAndActions"]["Class Features"].lower()
        elif phase_label == "rogue-l11-reliable":
            assert f["Character Level"] == "11" and f["Proficiency Bonus"] == "4"
            assert "6d6" in state["notesAndActions"]["Class Features"].lower()
        elif phase_label == "rogue-l20-capstone":
            assert f["Character Level"] == "20" and f["Proficiency Bonus"] == "6"
            assert "10d6" in state["notesAndActions"]["Class Features"].lower()
        elif phase_label == "rogue-l7-mixed":
            assert f["Character Level"] == "7" and f["Proficiency Bonus"] == "3"

    elif profile_name == "sorcerer":
        if phase_label == "sorcerer-l3-draconic":
            assert f["Character Level"] == "3"
            assert state["identity"]["sorcerer"] == {"level": 3, "subclass": "sorcerer-draconic"}
            mm = state["choices"]["classes"]["sorcerer"]["metamagic"]["extrachoices"]
            assert "quickened spell" in mm and "subtle spell" in mm, mm
            # 2024 Draconic Resilience AC = 10 + Dex (+2) + Cha (+4) = 16!
            assert int(f["AC"]) >= 16, ("Draconic Resilience AC expected >= 16", f["AC"])
        elif phase_label == "sorcerer-l6-spells":
            assert f["Character Level"] == "6"
            assert "sorcerer" in state["spells"]
            assert state["pages"] > 6
        elif phase_label == "sorcerer-l6-spend-rest":
            sp = find_row("Sorcery Points")
            assert sp["used"] in ("", "0"), sp
        elif phase_label == "sorcerer-l10-mixed":
            assert f["Character Level"] == "10" and f["Proficiency Bonus"] == "4"

    elif profile_name == "warlock":
        if phase_label == "warlock-l3-fiend":
            assert f["Character Level"] == "3"
            assert state["identity"]["warlock"] == {"level": 3, "subclass": "warlock-fiend"}
            inv = state["choices"]["classes"]["warlock"]["eldritch invocations"]["extrachoices"]
            assert "devil's sight" in inv and "armor of shadows" in inv, inv
            assert f["Feat Name 1"].lower().startswith("tough")
        elif phase_label == "warlock-l11-pact-spells":
            assert f["Character Level"] == "11" and f["Proficiency Bonus"] == "4"
            assert "warlock" in state["spells"]
            assert state["pages"] > 6
        elif phase_label == "warlock-l11-spend-rest":
            mc = find_row("Magical Cunning")
            assert mc["used"] in ("", "0"), mc
        elif phase_label == "warlock-l17-arcanum":
            assert f["Character Level"] == "17" and f["Proficiency Bonus"] == "6"
        elif phase_label == "warlock-l5-mixed":
            assert f["Character Level"] == "5" and f["Proficiency Bonus"] == "3"

    elif profile_name == "wizard":
        if phase_label == "wizard-l3-evoker":
            assert f["Character Level"] == "3"
            assert state["identity"]["wizard"] == {"level": 3, "subclass": "wizard-evoker"}
            assert state["choices"]["classes"]["wizard"]["scholar"]["choice"] == "arcana expertise"
            assert state["background"]["known"] == "sage"
        elif phase_label == "wizard-l10-empowered-spells":
            assert f["Character Level"] == "10" and f["Proficiency Bonus"] == "4"
            assert "wizard" in state["spells"]
            assert state["pages"] > 6
        elif phase_label == "wizard-l10-spend-rest":
            ar = find_row("Arcane Recovery")
            assert ar["used"] in ("", "0"), ar
        elif phase_label == "wizard-l6-mixed":
            assert f["Character Level"] == "6" and f["Proficiency Bonus"] == "3"

    elif profile_name == "multiclass":
        if phase_label == "mc-pal6-war3":
            assert f["Character Level"] == "9" and f["Proficiency Bonus"] == "4"
            assert set(state["identity"]) == {"paladin", "warlock"}
            assert state["identity"]["paladin"] == {"level": 6, "subclass": "paladin-devotion"}
            assert state["identity"]["warlock"] == {"level": 3, "subclass": "warlock-fiend"}
            assert f["HD1 Level"] and f["HD2 Level"], (f["HD1 Level"], f["HD2 Level"])
            assert "paladin" in state["spells"] and "warlock" in state["spells"]
            assert state["pages"] > 6
        elif phase_label == "mc-pal6-war3-rests":
            loh = find_row("Lay on Hands")
            assert loh["used"] == "20", ("Short rest must not reset Lay on Hands", loh)
        elif phase_label == "mc-ftr3-wiz5":
            assert f["Character Level"] == "8" and f["Proficiency Bonus"] == "3"
            assert set(state["identity"]) == {"fighter", "wizard"}
            assert "wizard" in state["spells"]
        elif phase_label == "mc-ftr5-wiz5-mixed":
            assert f["Character Level"] == "10" and f["Proficiency Bonus"] == "4"
