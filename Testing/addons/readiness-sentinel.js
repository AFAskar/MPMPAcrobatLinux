// Synthetic fixture for testing MPMB's manual add-on import and persistence.
var iFileName = "MPMB readiness sentinel.js";
WeaponsList["mpmb readiness blade"] = {
    regExpSearch: /mpmb readiness blade/i,
    name: "MPMB Readiness Blade",
    source: ["HB", 0],
    list: "melee",
    ability: 1,
    type: "Simple",
    damage: [1, 4, "slashing"],
    range: "Melee",
    weight: 1,
    description: "Synthetic testing fixture"
};
Value("Player Name", "MPMB add-on executed");
