import logging
import sys
import time
from collections import defaultdict
from datetime import datetime

import requests
from osmdiff import AugmentedDiff, Way

from filters import ChangeInBoundingBoxFilter
from src.users import UserInterest

logger = logging.getLogger(__name__)


# Monkey patch a fix on the Way class to fix the geometry building
def patched_way_geo_interface(self):
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


Way.__geo_interface__ = property(patched_way_geo_interface)


def work() -> int:

    user_filters = [
        UserInterest(
            user_id="iandees",
            filters=[
                # UserIDChangedFilter(user_id=4732),
                # UserIDMadeChangeFilter(user_id=4732),
                ChangeInBoundingBoxFilter(
                    bbox=(-94.240723, 44.486868, -92.164307, 45.323342),
                    name="Twin Cities",
                ),
            ],
        ),
    ]

    changesets = {}
    seqn_to_start = 6510021
    a = AugmentedDiff(sequence_number=seqn_to_start)
    a.base_url = "https://overpass.osmcha.org/api"

    # Get the most recent sequence number so we know if we need to sleep
    a.get_state()
    current_seqn = a.sequence_number
    logger.info("Most recent sequence number: %d", current_seqn)
    a.sequence_number = seqn_to_start

    while True:
        start_time = time.time()
        logger.info("Fetching changes from seqn %d", a.sequence_number)

        seqn_in_progress = a.sequence_number
        status = a.retrieve(clear_cache=True)
        a.sequence_number += 1
        # Convert the sequence number to a timestamp
        seqn_timestamp = datetime.fromtimestamp((seqn_in_progress + 22457216) * 60)
        logger.info(
            "Changes at seqn %d (time %s) with status %d: %s",
            seqn_in_progress,
            seqn_timestamp,
            status,
            a,
        )

        # Flatten changes to a list of (action, element) tuples
        changes = []
        for create in a.create:
            changes.append(("create", None, create))
        for modify in a.modify:
            changes.append(("modify", modify["old"], modify["new"]))
        for delete in a.delete:
            changes.append(("delete", delete["old"], delete["new"]))

        logger.info("Found %d changes", len(changes))

        # Gather unique changesets seen in the changes
        for action, old, new in changes:
            changeset_id = int(new.attribs["changeset"])
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
        changeset_response = requests.get(
            "https://api.openstreetmap.org/api/0.6/changesets?changesets={}".format(
                ",".join(map(str, changeset_ids_to_fetch))
            ),
            headers={"Accept": "application/json"},
        )
        changeset_response.raise_for_status()
        changeset_data = changeset_response.json()
        for changeset in changeset_data["changesets"]:
            changesets[changeset["id"]] = changeset

        # Have all changes and their changesets at this point, so run
        # processing to detect if someone cares about any of these changes
        interesting_changesets_by_user = {}
        for change in changes:
            for user_filter in user_filters:
                for filter in user_filter.filters:
                    if filter.matches(change):
                        if user_filter.user_id not in interesting_changesets_by_user:
                            interesting_changesets_by_user[user_filter.user_id] = (
                                defaultdict(set)
                            )

                        changeset_id = int(change[2].attribs["changeset"])
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

        # Move to the next sequence number after waiting a minute
        elapsed_time = time.time() - start_time

        # If we are caught up to the current sequence number, sleep for a minute
        if a.sequence_number >= current_seqn:
            wait_time = 60 - elapsed_time
        else:
            # Otherwise, sleep for 15 seconds to not hammer the server
            wait_time = 15 - elapsed_time
        wait_time = max(0.0, wait_time)
        logger.info("Elapsed time: %0.1f, sleeping %0.1f", elapsed_time, wait_time)
        time.sleep(wait_time)

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(work())
