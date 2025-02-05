# Helpers to stream augmented diffs from the OSMCha site.
import logging
import time
import xml.etree.ElementTree as ET
from typing import Iterator

import requests

from src.osm import OSMObject

ADIFF_SERVICE_URL_TEMPLATE = "https://adiffs.osmcha.org/replication/minute/{seqn}.adiff"


class ChangeContainer:
    def __init__(
        self,
        version: str,
        generator: str,
        note: str,
        creates: list["Action"],
        modifies: list["Action"],
        deletes: list["Action"],
    ):
        self.version = version
        self.generator = generator
        self.note = note
        self.creates = creates
        self.modifies = modifies
        self.deletes = deletes

    def __repr__(self):
        return "ChangeContainer(version={}, generator={}, note={}, creates={}, modifies={}, deletes={})".format(
            self.version,
            self.generator,
            self.note,
            self.creates,
            self.modifies,
            self.deletes,
        )

    @classmethod
    def from_element(cls, elem: ET.Element) -> "ChangeContainer":
        container = cls(
            version=elem.attrib["version"],
            generator=elem.attrib["generator"],
            note=elem.get("note"),
            creates=[],
            modifies=[],
            deletes=[],
        )

        for action_element in elem.findall("action"):
            action = Action.from_element(action_element)
            if action_element.attrib["type"] == "create":
                container.creates.append(action)
            elif action_element.attrib["type"] == "modify":
                container.modifies.append(action)
            elif action_element.attrib["type"] == "delete":
                container.deletes.append(action)

        return container

    def changes(self) -> list["Action"]:
        """
        :return: a list of all changes in this container
        """
        return self.creates + self.modifies + self.deletes


class Action:
    def __init__(self, action: str, old: OSMObject, new: OSMObject):
        self.action = action
        self.old = old
        self.new = new

    def __repr__(self):
        return "Action(action={}, old={}, new={})".format(
            self.action, self.old, self.new
        )

    @classmethod
    def from_element(cls, elem: ET.Element) -> "Action":
        old_element = elem.find("old/*")
        old_obj = (
            OSMObject.from_element(old_element) if old_element is not None else None
        )
        new_element = elem.find("new/*")
        new_obj = (
            OSMObject.from_element(new_element) if new_element is not None else None
        )
        return cls(action=elem.attrib["type"], old=old_obj, new=new_obj)


def stream_adiff(seqn: int = None) -> Iterator[ChangeContainer]:
    logger = logging.getLogger(__name__)

    while True:
        url = ADIFF_SERVICE_URL_TEMPLATE.format(seqn=seqn)
        logger.info("Fetching %s", url)
        resp = requests.get(url)

        if resp.status_code == 404:
            logger.info("No changes found for seqn %d, waiting 30 sec", seqn)
            time.sleep(30)
            continue

        resp.raise_for_status()

        # parse the adiff and yield the change
        tree = ET.fromstring(resp.content)
        container = ChangeContainer.from_element(tree)

        yield container

        seqn += 1
