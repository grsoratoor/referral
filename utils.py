import random
from functools import wraps


def telegram_html_escape(string: str):
    return string.replace("<", "&lt;") \
        .replace(">", "&gt;") \
        .replace("&", "&amp;") \
        .replace('"', "&quot;")


# Function to generate four options for the user to select
def generate_options(correct_sum):
    # Generate three random incorrect options
    incorrect_options = [correct_sum + random.randint(1, 5) for _ in range(3)]

    # Add the correct sum to the options
    options = [[str(option)] for option in incorrect_options + [correct_sum]]

    # Shuffle the options
    random.shuffle(options)

    return options



