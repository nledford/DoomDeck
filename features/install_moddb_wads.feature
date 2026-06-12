Feature: Install additional ModDB WADs

  Scenario: Installing a map archive adds playable WADs to the PWAD folder
    Given the user has an existing DoomDeck managed folder
    And a ModDB archive contains a playable WAD and documentation
    When the user runs DoomDeck install-wads for that archive
    Then the playable WAD is installed in the PWAD folder
    And documentation files are not installed as playable content
    And DoomRunner content groups are refreshed

  Scenario: Installing WADs does not perform full setup discovery
    Given the user only wants to add PWAD content
    When the user runs DoomDeck install-wads
    Then DoomDeck does not require Steam app discovery
    And DoomDeck does not add or update Steam shortcuts
