import logging

import shapely
from osmdiff import Node, Way
from osmdiff.osm import OSMObject, Relation


class ChangeFilter:
    def matches(self, change: tuple[str, OSMObject, OSMObject]) -> bool:
        """Returns True if the change matches the filter."""
        raise NotImplementedError()

    def explanation(self) -> str:
        """Returns a human-readable explanation of the filter."""
        raise NotImplementedError()


class UserIDChangedFilter(ChangeFilter):
    """
    Triggers on changes where the last touched user ID of the object has changed from the given user to someone else.
    """

    def __init__(self, user_id: int):
        # Converting to string here because the OSM data will be strings
        self.user_id = str(user_id)

    def explanation(self) -> str:
        return f"User ID changed from {self.user_id}"

    def matches(self, change: tuple[str, OSMObject, OSMObject]) -> bool:
        action, old, new = change
        return (
            old
            and new
            and old.attribs["uid"] == self.user_id
            and new.attribs["uid"] != self.user_id
        )


class UserIDMadeChangeFilter(ChangeFilter):
    """
    Triggers on changes where the last touched user ID of the object has changed to the given user.
    """

    def __init__(self, user_id: int):
        # Converting to string here because the OSM data will be strings
        self.user_id = str(user_id)
        self.logger = logging.getLogger(__name__)

    def explanation(self) -> str:
        return f"User ID {self.user_id} made a change"

    def matches(self, change: tuple[str, OSMObject, OSMObject]) -> bool:
        action, old, new = change
        return new and new.attribs["uid"] == self.user_id


class NewUserFilter(ChangeFilter):
    """
    Triggers on changes where we haven't seen the user ID before in the given user ID set.

    New users will be added to the set after they are seen.
    """

    def __init__(self, user_ids: set[int]):
        self.user_ids = user_ids

    def explanation(self) -> str:
        return "New user made a change"

    def matches(self, change: tuple[str, OSMObject, OSMObject]) -> bool:
        action, old, new = change

        if not new:
            return False

        user_id = int(new.attribs["uid"])

        if user_id not in self.user_ids:
            self.user_ids.add(user_id)
            return True

        return False


class ObjectChangedFilter(ChangeFilter):
    """
    Triggers on changes where the object of type `obj_type` with the given ID has changed.
    """

    def __init__(self, obj_type: str, id: int):
        self.obj_type = obj_type

        if obj_type not in ("node", "way", "relation"):
            raise ValueError("Invalid object type: {}".format(obj_type))

        self.obj_id = str(id)

    def explanation(self) -> str:
        return f"Object {self.obj_type} {self.obj_id} changed"

    def matches(self, change: tuple[str, OSMObject, OSMObject]) -> bool:
        action, old, new = change

        # The old and new will be the same type and id, so pick the first one that exists
        thing_to_check = old or new

        if self.obj_type == "node" and not isinstance(thing_to_check, Node):
            return False
        if self.obj_type == "way" and not isinstance(thing_to_check, Way):
            return False
        if self.obj_type == "relation" and not isinstance(thing_to_check, Relation):
            return False

        return thing_to_check.attribs["id"] == self.obj_id


class ChangeInShapeFilter(ChangeFilter):
    """
    Triggers on changes where either old or new object intersects the given shape.
    """

    def __init__(self, shape: shapely.Polygon, name: str = None):
        self.shape = shape
        self.name = name

        # Prepare the shape for faster intersection checks
        shapely.prepare(self.shape)

    def explanation(self) -> str:
        return f'Change in shape "{self.name}"' if self.name else "Change in shape"

    def matches(self, change: tuple[str, OSMObject, OSMObject]) -> bool:
        action, old, new = change

        # TODO Skip relations for now because geometry checks are more difficult
        if isinstance(old, Relation) or isinstance(new, Relation):
            return False

        old_shape = None
        if old and old.attribs.get("visible") != "false":
            old_shape = shapely.geometry.shape(old)

        new_shape = None
        if new and new.attribs.get("visible") != "false":
            new_shape = shapely.geometry.shape(new)

        # If the old and new object have the same changeset id, then it's likely
        # a way whose nodes have changed position. We're going to ignore that
        # change because the node change will cause the changeset to be included.
        if old and new and old.attribs["changeset"] == new.attribs["changeset"]:
            return False

        thing_to_check = new_shape or old_shape

        return thing_to_check and thing_to_check.intersects(self.shape)


class ChangeInBoundingBoxFilter(ChangeInShapeFilter):
    """
    Triggers on changes where either old or new object intersects the given bounding box.

    Bounding box is represented as minlon, minlat, maxlon, maxlat.
    """

    def __init__(self, bbox: tuple[float, float, float, float], name: str = None):
        bbox_geojson = {
            "type": "Polygon",
            "coordinates": [
                [
                    [bbox[0], bbox[1]],
                    [bbox[0], bbox[3]],
                    [bbox[2], bbox[3]],
                    [bbox[2], bbox[1]],
                    [bbox[0], bbox[1]],
                ]
            ],
        }
        super().__init__(
            shapely.geometry.shape(bbox_geojson), name=name or f"bbox {bbox}"
        )


class TagValueInListFilter(ChangeFilter):
    """
    Triggers on changes where an object's tag with the given key has changed to one of the given values.
    """

    def __init__(self, tag: str, values: list[str]):
        self.tag = tag
        self.values = values

    def explanation(self) -> str:
        if len(self.values) > 3:
            return f"Tag {self.tag} changed to one of {self.values[:3]} and {len(self.values) - 3} more"

        return f"Tag {self.tag} changed to one of {self.values}"

    def matches(self, change: tuple[str, OSMObject, OSMObject]) -> bool:
        action, old, new = change

        old_value = old.tags.get(self.tag) if old else None
        new_value = new.tags.get(self.tag) if new else None

        return (old_value != new_value) and (new_value in self.values)
