from assessment.big_five_questions import BIG_FIVE_DIMENSIONS, TOTAL_QUESTIONS as BIG_FIVE_TOTAL, calculate_all_scores as calculate_big_five_scores
from assessment.sternberg_questions import TOTAL_QUESTIONS as STERNBERG_TOTAL, calculate_all_scores as calculate_sternberg_scores, get_primary_love_type


def test_big_five_question_count_and_scores() -> None:
    assert BIG_FIVE_TOTAL == 50
    scores = calculate_big_five_scores([3] * BIG_FIVE_TOTAL)
    assert set(scores.keys()) == set(BIG_FIVE_DIMENSIONS)
    assert all(45 <= value <= 55 for value in scores.values())


def test_sternberg_question_count_and_types() -> None:
    assert STERNBERG_TOTAL == 15
    assert get_primary_love_type({"intimacy": 80, "passion": 80, "commitment": 80}) == "consummate_love"
    assert get_primary_love_type({"intimacy": 20, "passion": 80, "commitment": 20}) == "infatuation"
    scores = calculate_sternberg_scores([5] * STERNBERG_TOTAL)
    assert set(scores.keys()) == {"intimacy", "passion", "commitment"}
    assert all(45 <= value <= 55 for value in scores.values())
