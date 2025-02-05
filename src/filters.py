import shapely

from src.adiff import Action
from src.osm import OSMType


class ChangeFilter:
    def matches(self, change: Action) -> bool:
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
        self.user_id = user_id

    def explanation(self) -> str:
        return f"User ID changed from {self.user_id}"

    def matches(self, change: Action) -> bool:
        action, old, new = change.action, change.old, change.new
        return old and new and old.uid == self.user_id and new.uid != self.user_id


class UserIDMadeChangeFilter(ChangeFilter):
    """
    Triggers on changes where the last touched user ID of the object has changed to the given user.
    """

    def __init__(self, user_id: int):
        self.user_id = user_id

    def explanation(self) -> str:
        return f"User ID {self.user_id} made a change"

    def matches(self, change: Action) -> bool:
        action, old, new = change.action, change.old, change.new
        return new and new.uid == self.user_id


class NewUserFilter(ChangeFilter):
    """
    Triggers on changes where we haven't seen the user ID before in the given user ID set.

    New users will be added to the set after they are seen.
    """

    def __init__(self, user_ids: set[int]):
        self.user_ids = user_ids

    def explanation(self) -> str:
        return "New user made a change"

    def matches(self, change: Action) -> bool:
        action, old, new = change.action, change.old, change.new

        if not new:
            return False

        if new.uid not in self.user_ids:
            self.user_ids.add(new.uid)
            return True

        return False


class ObjectChangedFilter(ChangeFilter):
    """
    Triggers on changes where the object of type `obj_type` with the given ID has changed.
    """

    def __init__(self, obj_type: OSMType, id: int):
        self.obj_type = obj_type
        self.obj_id = id

    def explanation(self) -> str:
        return f"Object {self.obj_type} {self.obj_id} changed"

    def matches(self, change: Action) -> bool:
        action, old, new = change.action, change.old, change.new

        # The old and new will be the same type and id, so pick the first one that exists
        thing_to_check = old or new

        if thing_to_check.type != self.obj_type:
            return False

        return thing_to_check.id == self.obj_id


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

    def matches(self, change: Action) -> bool:
        action, old, new = change.action, change.old, change.new

        # TODO Skip relations for now because geometry checks are more difficult
        if (old and old.type == OSMType.RELATION) or (
            new and new.type == OSMType.RELATION
        ):
            return False

        old_shape = None
        if old and old.visible:
            old_shape = shapely.geometry.shape(old)

        new_shape = None
        if new and new.visible:
            new_shape = shapely.geometry.shape(new)

        # If the old and new object have the same changeset id, then it's likely
        # a way whose nodes have changed position. We're going to ignore that
        # change because the node change will cause the changeset to be included.
        if old and new and old.changeset == new.changeset:
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

    def matches(self, change: Action) -> bool:
        action, old, new = change.action, change.old, change.new

        old_value = old.tags.get(self.tag) if old else None
        new_value = new.tags.get(self.tag) if new else None

        return (old_value != new_value) and (new_value in self.values)


class ObjectWithTagChangedFilter(ChangeFilter):
    """
    Triggers when an object with the given tag key and value has changed.
    """

    def __init__(self, tag: str, value: str):
        self.tag = tag
        self.value = value

    def explanation(self) -> str:
        return f"Object with tag {self.tag}={self.value} changed"

    def matches(self, change: Action) -> bool:
        action, old, new = change.action, change.old, change.new

        # Check if the old object has the given key and value
        old_has_tag = old and old.tags.get(self.tag) == self.value

        # Check if the new object has the given key and value
        new_has_tag = new and new.tags.get(self.tag) == self.value

        # Return true if the old object had the tag and something changed, or if a new object with the tag was created
        return (old_has_tag and (old != new)) or (action == "create" and new_has_tag)
