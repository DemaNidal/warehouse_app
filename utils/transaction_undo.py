from sqlalchemy import func

from models import db, InventoryTransaction, InventoryLocation


def _latest_transaction_id_per_location(location_ids):
    """Map each location id to the id of the most recent transaction that
    touched it, either as the source (location_id) or as a transfer
    destination (destination_location_id)."""

    if not location_ids:
        return {}

    by_source = dict(
        db.session.query(
            InventoryTransaction.location_id,
            func.max(InventoryTransaction.id)
        )
        .filter(InventoryTransaction.location_id.in_(location_ids))
        .group_by(InventoryTransaction.location_id)
        .all()
    )

    by_destination = dict(
        db.session.query(
            InventoryTransaction.destination_location_id,
            func.max(InventoryTransaction.id)
        )
        .filter(InventoryTransaction.destination_location_id.in_(location_ids))
        .group_by(InventoryTransaction.destination_location_id)
        .all()
    )

    latest = {}
    for loc_id in location_ids:
        candidates = [
            v for v in (by_source.get(loc_id), by_destination.get(loc_id))
            if v is not None
        ]
        latest[loc_id] = max(candidates) if candidates else None

    return latest


def _locations_touched(transaction):
    touched = [transaction.location_id]
    if transaction.destination_location_id:
        touched.append(transaction.destination_location_id)
    return touched


def compute_undoable_transaction_ids(transactions):
    """Given an iterable of InventoryTransaction rows, return the subset of
    their ids that are safe to undo — i.e. no later transaction has touched
    any location they touched."""

    location_ids = set()
    for t in transactions:
        location_ids.update(_locations_touched(t))

    latest_by_location = _latest_transaction_id_per_location(location_ids)

    undoable_ids = set()
    for t in transactions:
        if all(
            latest_by_location.get(loc_id) == t.id
            for loc_id in _locations_touched(t)
        ):
            undoable_ids.add(t.id)

    return undoable_ids


def is_transaction_undoable(transaction):
    return transaction.id in compute_undoable_transaction_ids([transaction])


def _delete_location_if_now_empty(location):
    """Mirrors the safety rule in delete_location(): only remove a location
    automatically if it is empty and has no transaction history left at all."""

    if location.quantity != 0:
        return

    has_history = InventoryTransaction.query.filter(
        db.or_(
            InventoryTransaction.location_id == location.id,
            InventoryTransaction.destination_location_id == location.id
        )
    ).first() is not None

    if not has_history:
        db.session.delete(location)


def undo_transaction(transaction):
    """Reverses the inventory effect of `transaction` and deletes it.
    Caller must have already verified is_transaction_undoable(transaction)
    inside the same locked transaction to avoid a race condition."""

    if transaction.transaction_type == "TRANSFER":
        source = InventoryLocation.query.filter_by(
            id=transaction.location_id
        ).with_for_update().first()

        destination = InventoryLocation.query.filter_by(
            id=transaction.destination_location_id
        ).with_for_update().first()

        if transaction.quantity_before is not None:
            source.quantity = transaction.quantity_before
        else:
            source.quantity += transaction.quantity

        destination.quantity -= transaction.quantity

        db.session.delete(transaction)
        db.session.flush()

        _delete_location_if_now_empty(source)
        _delete_location_if_now_empty(destination)

    else:
        location = InventoryLocation.query.filter_by(
            id=transaction.location_id
        ).with_for_update().first()

        if transaction.transaction_type == "IN":
            location.quantity = (
                transaction.quantity_before
                if transaction.quantity_before is not None
                else location.quantity - transaction.quantity
            )
        elif transaction.transaction_type == "OUT":
            location.quantity = (
                transaction.quantity_before
                if transaction.quantity_before is not None
                else location.quantity + transaction.quantity
            )
        elif transaction.transaction_type == "ADJUSTMENT":
            if transaction.quantity_before is not None:
                location.quantity = transaction.quantity_before

        db.session.delete(transaction)
        db.session.flush()

        _delete_location_if_now_empty(location)
