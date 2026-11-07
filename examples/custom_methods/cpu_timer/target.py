"""Small CPU workload used to demonstrate real method-controlled invocations."""

calls = 0


def work(iterations):
    global calls
    calls += 1
    return sum(range(iterations))
