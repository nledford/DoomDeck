Feature: Install a playable DoomRunner Steam shortcut

  Scenario: First install creates one launchable DoomRunner shortcut
    Given a Steam user has DOOM + DOOM II installed
    And DoomDeck can install DoomRunner, UZDoom, an IWAD, and Brutal Doom
    When the user runs DoomDeck install
    Then Steam has exactly one Doom Runner shortcut
    And Steam has a DoomDeck Steam Input profile for the Doom Runner shortcut
    And DoomRunner has a UZDoom engine configured
    And DoomRunner has a Brutal Doom preset with an existing IWAD and mod file
    And the preset launch paths resolve to existing files

  Scenario: Re-running install updates the setup without duplicate shortcuts
    Given DoomDeck has already created a Doom Runner shortcut
    And an older DoomDeck preset shortcut also exists
    When the user runs DoomDeck install again
    Then Steam still has exactly one Doom Runner shortcut
    And no DoomDeck preset shortcuts remain
