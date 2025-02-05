import logging
import sys
from collections import defaultdict

from filters import (
    ChangeInBoundingBoxFilter,
    UserIDMadeChangeFilter,
    UserIDChangedFilter,
)
from src.adiff import stream_adiff
from src.filters import TagValueInListFilter
from src.osm import OSMAPI
from src.users import UserInterest

logger = logging.getLogger(__name__)


def work() -> int:

    user_filters = [
        UserInterest(
            user_id="iandees",
            filters=[
                UserIDChangedFilter(user_id=4732),
                UserIDMadeChangeFilter(user_id=4732),
                TagValueInListFilter("name", ["stupid", "dumb"]),
                ChangeInBoundingBoxFilter(
                    bbox=(-94.240723, 44.486868, -92.164307, 45.323342),
                    name="Twin Cities",
                ),
                ChangeInBoundingBoxFilter(
                    bbox=(-91.761932, 45.858402, -90.723724, 46.268136),
                    name="Hayward",
                ),
            ],
        ),
    ]

    osm_api = OSMAPI()

    changesets = {}
    seqn_to_start = 6460395
    for diff in stream_adiff(seqn=seqn_to_start):
        logger.info("Found %d changes", len(diff.changes()))

        # Gather unique changesets seen in the changes
        for change in diff.changes():
            changeset_id = change.new.changeset
            if changeset_id not in changesets:
                changesets[changeset_id] = None

        # Fetch changesets that don't have any details yet
        changeset_ids_to_fetch = [
            changeset_id
            for changeset_id in changesets.keys()
            if not changesets.get(changeset_id)
        ]
        logger.info(
            "Fetching metadata for %d changesets we have not seen yet",
            len(changeset_ids_to_fetch),
        )

        changeset_data = osm_api.changesets(changeset_ids_to_fetch)
        for changeset in changeset_data:
            changesets[changeset.id] = changeset

        # Have all changes and their changesets at this point, so run
        # processing to detect if someone cares about any of these changes
        interesting_changesets_by_user = {}
        for change in diff.changes():
            for user_filter in user_filters:
                for filter in user_filter.filters:
                    if filter.matches(change):
                        if user_filter.user_id not in interesting_changesets_by_user:
                            interesting_changesets_by_user[user_filter.user_id] = (
                                defaultdict(set)
                            )

                        changeset_id = change.new.changeset
                        explanation = filter.explanation()

                        interesting_changesets_by_user[user_filter.user_id][
                            explanation
                        ].add(changeset_id)

        for user_id, explanations in interesting_changesets_by_user.items():
            logger.info("⚠️User %s interesting changesets", user_id)
            for explanation, changeset_ids in explanations.items():
                logger.info("  %s: %s", explanation, changeset_ids)

        if not interesting_changesets_by_user:
            logger.info("😭 No interesting changesets found in this batch of changes")

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(work())
