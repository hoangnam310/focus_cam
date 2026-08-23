from focuscam.video import even


def test_even_dimensions() -> None:
    assert even(721) == 720
    assert even(720) == 720
    assert even(1) == 2
