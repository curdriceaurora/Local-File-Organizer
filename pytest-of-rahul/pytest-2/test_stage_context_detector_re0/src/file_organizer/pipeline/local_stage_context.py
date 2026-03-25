class StageContext:
    pass
def f() -> None:
    ctx = StageContext()
    object.__setattr__(ctx, 'category', 'x')
