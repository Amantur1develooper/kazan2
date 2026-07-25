from decimal import Decimal
from apps.estimates.models import ExpenseAllocation, EstimateItem, EstimateSection


def resolve_and_allocate(floor_expense) -> bool:
    """
    Auto-allocate floor_expense to an estimate item.
    Returns True if allocated to a real item, False if went to «Прочие расходы».
    Never raises.

    Priority:
    1. Manual allocation already exists → skip (do nothing)
    2. Estimate for this block exists? Find EstimateItem in same stage's top section
       matching floor_expense.name (case-insensitive). Exactly one match → allocate 100%.
    3. Otherwise → find/create «Прочие расходы» section under the stage's top section
       and allocate there (estimate_item=None means unlinked).
    """
    # Step 1: already allocated manually
    if floor_expense.allocations.exists():
        return True

    block = floor_expense.floor.stage.block

    # Find estimate for block
    try:
        from apps.estimates.models import Estimate
        estimate = Estimate.objects.get(block=block)
    except Estimate.DoesNotExist:
        return False

    # Stage name matches top-level section name (set during sync)
    stage = floor_expense.floor.stage
    # Find top-level section matching this stage
    top_section = EstimateSection.objects.filter(
        estimate=estimate,
        parent__isnull=True,
        name=stage.name,
    ).first()

    if not top_section:
        # Try matching by partial name (stage name may include code prefix)
        top_section = EstimateSection.objects.filter(
            estimate=estimate,
            parent__isnull=True,
        ).filter(
            name__icontains=stage.name.split(' ', 1)[-1][:20]
        ).first()

    qty = floor_expense.quantity
    amount = floor_expense.total_amount

    # Step 2: find matching item under this stage
    if top_section:
        candidates = EstimateItem.objects.filter(
            section__estimate=estimate,
            section__parent=top_section,
            name__iexact=floor_expense.name,
        )
        if not candidates.exists():
            candidates = EstimateItem.objects.filter(
                section__estimate=estimate,
                section__parent=top_section,
                name__icontains=floor_expense.name[:30],
            )
        if candidates.count() == 1:
            item = candidates.first()
            ExpenseAllocation.objects.update_or_create(
                floor_expense=floor_expense,
                estimate_item=item,
                defaults={'quantity': qty, 'amount': amount},
            )
            return True

    # Step 3: allocate to «Прочие расходы» (estimate_item=None = unlinked)
    ExpenseAllocation.objects.update_or_create(
        floor_expense=floor_expense,
        estimate_item=None,
        defaults={'quantity': qty, 'amount': amount, 'note': 'Нераспределено'},
    )
    return False
