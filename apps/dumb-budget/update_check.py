def check(current_version: str) -> dict:
    # DumbWareio/DumbBudget has no versioned GitHub releases or git tags;
    # the Docker image is published as :latest only. Version tracking is not possible.
    raise NotImplementedError(
        "DumbBudget has no versioned releases — image is published as :latest only"
    )
