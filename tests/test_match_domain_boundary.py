import unittest

from match_domain.boundary import (
    RECOMMENDATION_STATUS_OWNER,
    case_progress_owner,
    case_status_owner,
)


class MatchDomainBoundaryTests(unittest.TestCase):
    def test_proxy_intro_case_status_owner(self) -> None:
        self.assertEqual(case_status_owner("proxy_intro"), RECOMMENDATION_STATUS_OWNER)

    def test_matchmaking_case_status_owner(self) -> None:
        self.assertEqual(case_status_owner("matchmaking"), "matchmaking")

    def test_case_progress_owner_from_case_type(self) -> None:
        self.assertEqual(
            case_progress_owner({"case_type": "proxy_intro", "case_status": "awaiting_reply"}),
            RECOMMENDATION_STATUS_OWNER,
        )
        self.assertEqual(
            case_progress_owner({"case_type": "matchmaking", "case_status": "pending_first_contact"}),
            "matchmaking",
        )


if __name__ == "__main__":
    unittest.main()
