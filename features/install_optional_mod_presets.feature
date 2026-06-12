Feature: Generate only launchable optional mod presets

  Scenario: Modded presets are omitted when managed mod files are absent
    Given DoomDeck has a usable Doom II IWAD
    And Brutal Doom is not installed
    And Project Brutality is not installed
    When DoomDeck generates DoomRunner presets
    Then DoomRunner includes Vanilla Doom and UZDoom presets
    But DoomRunner does not include Brutal Doom or Project Brutality presets

  Scenario: Installed managed mods become presets
    Given DoomDeck has a usable Doom II IWAD
    And Brutal Doom is installed as a managed mod alias
    When DoomDeck generates DoomRunner presets
    Then DoomRunner includes the Brutal Doom preset
    And the preset references the managed Brutal Doom file
