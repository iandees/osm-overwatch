# Models for OSM data
import xml.etree.ElementTree as ET
from datetime import datetime
from enum import Enum

import requests


class OSMType(Enum):
    NODE = "node"
    WAY = "way"
    RELATION = "relation"


class OSMObject:
    def __init__(
        self,
        _type: OSMType,
        _id: int,
        version: int,
        timestamp: datetime,
        uid: int,
        user: str,
        changeset: int,
        visible: bool,
        tags: dict[str, str],
    ):
        self.type = _type
        self.id = _id
        self.version = version
        self.timestamp = timestamp
        self.uid = uid
        self.user = user
        self.changeset = changeset
        self.visible = visible
        self.tags = tags

    @classmethod
    def from_element(cls, element: ET.Element) -> "OSMObject":
        if element.tag == "node":
            return Node.from_xml(element)
        elif element.tag == "way":
            return Way.from_xml(element)
        elif element.tag == "relation":
            return Relation.from_xml(element)
        raise ValueError("Unknown element type: {}".format(element.tag))


class Node(OSMObject):
    def __init__(
        self,
        _id: int,
        version: int,
        timestamp: datetime,
        uid: int,
        user: str,
        changeset: int,
        visible: bool,
        tags: dict[str, str],
        lat: float,
        lon: float,
    ):
        super().__init__(
            OSMType.NODE,
            _id,
            version,
            timestamp,
            uid,
            user,
            changeset,
            visible,
            tags,
        )
        self.lat = lat
        self.lon = lon

    @classmethod
    def from_xml(cls, elem: ET.Element):
        # Note that osmx doesn't support metadata for untagged nodes, so it's
        # possible for a node to only have the ID present in the augmented diff
        return cls(
            _id=int(elem.attrib["id"]),
            version=int(elem.attrib["version"]) if elem.attrib.get("version") else None,
            timestamp=(
                datetime.fromisoformat(elem.attrib["timestamp"])
                if elem.attrib.get("timestamp")
                else None
            ),
            uid=int(elem.attrib["uid"]) if elem.attrib.get("uid") else None,
            user=elem.attrib["user"] if elem.attrib.get("user") else None,
            changeset=(
                int(elem.attrib["changeset"]) if elem.attrib.get("changeset") else None
            ),
            visible=elem.attrib.get("visible") != "false",
            tags={tag.attrib["k"]: tag.attrib["v"] for tag in elem.findall("tag")},
            lat=float(elem.attrib["lat"]) if elem.attrib.get("lat") else None,
            lon=float(elem.attrib["lon"]) if elem.attrib.get("lon") else None,
        )

    @property
    def __geo_interface__(self):
        return {
            "type": "Point",
            "coordinates": (self.lon, self.lat),
        }


class Way(OSMObject):
    def __init__(
        self,
        _id: int,
        version: int,
        timestamp: datetime,
        uid: int,
        user: str,
        changeset: int,
        visible: bool,
        tags: dict[str, str],
        nodes: list["NodeRef"],
    ):
        super().__init__(
            OSMType.WAY,
            _id,
            version,
            timestamp,
            uid,
            user,
            changeset,
            visible,
            tags,
        )
        self.nodes = nodes

    @classmethod
    def from_xml(cls, elem: ET.Element):
        # Similar to Nodes, osmx doesn't support metadata for untagged ways, so it's possible
        # for ways to only have the ID present in the augmented diff
        return cls(
            _id=int(elem.attrib["id"]),
            version=int(elem.attrib["version"]),
            timestamp=(
                datetime.fromisoformat(elem.attrib["timestamp"])
                if elem.attrib.get("timestamp")
                else None
            ),
            uid=int(elem.attrib["uid"]) if elem.attrib.get("uid") else None,
            user=elem.attrib["user"] if elem.attrib.get("user") else None,
            changeset=(
                int(elem.attrib["changeset"]) if elem.attrib.get("changeset") else None
            ),
            visible=elem.attrib.get("visible") != "false",
            tags={tag.attrib["k"]: tag.attrib["v"] for tag in elem.findall("tag")},
            nodes=[NodeRef.from_xml(node) for node in elem.findall("nd")],
        )

    @property
    def __geo_interface__(self):
        if not self.nodes:
            # If the way was deleted and only the ID is present in the diff, there won't be any nodes
            # to build a geometry from
            return {
                "type": "Polygon",
                "coordinates": [],
            }

        if self.nodes[0] == self.nodes[-1]:
            return {
                "type": "Polygon",
                "coordinates": [[[n.lon, n.lat] for n in self.nodes]],
            }
        else:
            return {
                "type": "LineString",
                "coordinates": [[n.lon, n.lat] for n in self.nodes],
            }


class NodeRef:
    def __init__(self, ref: int, lat: float = None, lon: float = None):
        self.ref = ref
        self.lat = None
        self.lon = None

    @classmethod
    def from_xml(cls, elem: ET.Element):
        return cls(
            ref=int(elem.attrib["ref"]),
            lat=float(elem.attrib["lat"]) if elem.attrib.get("lat") else None,
            lon=float(elem.attrib["lon"]) if elem.attrib.get("lon") else None,
        )


class RelationMember:
    def __init__(self, _type: OSMType, _ref: int, role: str):
        self.type = _type
        self.ref = _ref
        self.role = role


class Relation(OSMObject):
    def __init__(
        self,
        _id: int,
        version: int,
        timestamp: datetime,
        uid: int,
        user: str,
        changeset: int,
        visible: bool,
        tags: dict[str, str],
        members: list[RelationMember],
    ):
        super().__init__(
            OSMType.RELATION,
            _id,
            version,
            timestamp,
            uid,
            user,
            changeset,
            visible,
            tags,
        )
        self.members = members

    @classmethod
    def from_xml(cls, elem: ET.Element):
        return cls(
            _id=int(elem.attrib["id"]),
            version=int(elem.attrib["version"]),
            timestamp=datetime.fromisoformat(elem.attrib["timestamp"]),
            uid=int(elem.attrib["uid"]),
            user=elem.attrib["user"],
            changeset=int(elem.attrib["changeset"]),
            visible=elem.attrib.get("visible") != "false",
            tags={tag.attrib["k"]: tag.attrib["v"] for tag in elem.findall("tag")},
            members=[
                RelationMember(
                    _type=OSMType(tag.attrib["type"]),
                    _ref=int(tag.attrib["ref"]),
                    role=tag.attrib["role"],
                )
                for tag in elem.findall("member")
            ],
        )

    @property
    def __geo_interface__(self):
        raise NotImplementedError(
            "Relation __geo_interface__ not implemented for Relations yet"
        )


class Changeset:
    def __init__(
        self,
        _id: int,
        created_at: datetime,
        closed_at: datetime,
        open: bool,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
        user_id: int,
        user_name: str,
        comments_count: int,
        tags: dict[str, str],
    ):
        self.id = _id
        self.created_at = created_at
        self.closed_at = closed_at
        self.open = open
        self.min_lat = min_lat
        self.min_lon = min_lon
        self.max_lat = max_lat
        self.max_lon = max_lon
        self.user_id = user_id
        self.user_name = user_name
        self.comments_count = comments_count
        self.tags = tags

    @classmethod
    def from_element(cls, elem: ET.Element) -> "Changeset":
        return cls(
            _id=int(elem.attrib["id"]),
            created_at=datetime.fromisoformat(elem.attrib["created_at"]),
            closed_at=(
                datetime.fromisoformat(elem.attrib["closed_at"])
                if elem.attrib.get("closed_at")
                else None
            ),
            open=elem.attrib["open"] == "true",
            min_lat=(
                float(elem.attrib["min_lat"]) if elem.attrib.get("min_lat") else None
            ),
            min_lon=(
                float(elem.attrib["min_lon"]) if elem.attrib.get("min_lon") else None
            ),
            max_lat=(
                float(elem.attrib["max_lat"]) if elem.attrib.get("max_lat") else None
            ),
            max_lon=(
                float(elem.attrib["max_lon"]) if elem.attrib.get("max_lon") else None
            ),
            user_id=int(elem.attrib["uid"]),
            user_name=elem.attrib["user"],
            comments_count=int(elem.attrib["comments_count"]),
            tags={tag.attrib["k"]: tag.attrib["v"] for tag in elem.findall("tag")},
        )


class OSMAPI:
    def __init__(self, url: str = "https://api.openstreetmap.org/api/0.6"):
        self.url = url
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/xml",
                "User-Agent": "OSM Overwatch",
            }
        )

    def changeset(self, changeset_id: int) -> Changeset:
        """
        :param changeset_id: ID of the changeset to fetch
        :return: The changeset object for the given ID
        """
        response = self.session.get(
            f"{self.url}/changesets/{changeset_id}", stream=True
        )
        response.raise_for_status()
        return Changeset.from_element(ET.fromstring(response.content))

    def changesets(self, changeset_ids_to_fetch: list[int]) -> list[Changeset]:
        """
        :param changeset_ids_to_fetch: a list of changeset IDs to fetch
        :return: a list of changeset objects for the given IDs
        """
        response = self.session.get(
            f"{self.url}/changesets",
            params={"changesets": ",".join(map(str, changeset_ids_to_fetch))},
            stream=True,
        )
        response.raise_for_status()
        return [
            Changeset.from_element(elem) for elem in ET.fromstring(response.content)
        ]
