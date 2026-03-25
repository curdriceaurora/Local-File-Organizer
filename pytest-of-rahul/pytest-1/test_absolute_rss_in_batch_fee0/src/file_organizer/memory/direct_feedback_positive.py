
def tune(process, sizer):
    sizer.adjust_from_feedback(process.memory_info().rss)
