# src/utils/metrics.py

def calculate_average_queries(results):
    if not results:
        return 0

    total = sum(item["attempts"] for item in results)
    return total / len(results)


def count_samples(results):
    return len(results)