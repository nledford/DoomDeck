from __future__ import annotations

from collections import OrderedDict
from typing import cast

import pytest

from doomdeck.domain.models import DoomDeckError
from doomdeck.infrastructure.steam_compat import (
    TextVDFObject,
    compat_mapping_key,
    dumps_text_vdf,
    loads_text_vdf,
    set_compat_tool_mapping,
)


def test_text_vdf_round_trips_nested_key_values() -> None:
    data = cast(
        TextVDFObject,
        OrderedDict(
            {
                "UserLocalConfigStore": OrderedDict(
                    {
                        "Software": OrderedDict(
                            {
                                "Valve": OrderedDict(
                                    {
                                        "Steam": OrderedDict(
                                            {
                                                "CompatToolMapping": OrderedDict(
                                                    {
                                                        "123": OrderedDict(
                                                            {
                                                                "name": "proton_10",
                                                                "config": "",
                                                                "priority": "250",
                                                            }
                                                        )
                                                    }
                                                )
                                            }
                                        )
                                    }
                                )
                            }
                        )
                    }
                )
            }
        ),
    )

    assert loads_text_vdf(dumps_text_vdf(data)) == data


def test_text_vdf_parser_rejects_malformed_input() -> None:
    with pytest.raises(DoomDeckError, match="Could not parse Steam text VDF"):
        loads_text_vdf('"UserLocalConfigStore" { "Software"')


def test_compat_mapping_key_uses_unsigned_shortcut_appid() -> None:
    assert compat_mapping_key(-1) == "4294967295"
    assert compat_mapping_key(42) == "42"


def test_set_compat_tool_mapping_creates_nested_steam_mapping() -> None:
    root: OrderedDict[str, object] = OrderedDict({"UserLocalConfigStore": OrderedDict()})

    set_compat_tool_mapping(root, appid=-1, compat_tool="proton_10")

    user_store = cast(TextVDFObject, root["UserLocalConfigStore"])
    software = cast(TextVDFObject, user_store["Software"])
    valve = cast(TextVDFObject, software["Valve"])
    steam = cast(TextVDFObject, valve["Steam"])
    mapping = cast(TextVDFObject, steam["CompatToolMapping"])
    assert mapping["4294967295"] == OrderedDict(
        {
            "name": "proton_10",
            "config": "",
            "priority": "250",
        }
    )
