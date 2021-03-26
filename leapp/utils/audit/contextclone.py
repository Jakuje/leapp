from leapp.utils.audit import dict_factory, get_connection


def _fetch_table_for_context(db, table, context):
    cursor = db.execute('''
            SELECT * FROM {table} WHERE context = ?
        '''.format(table=table), (context,))
    cursor.row_factory = dict_factory
    while True:
        row = cursor.fetchone()
        if not row:
            break
        yield row
    del cursor


def _row_tuple(row, *fields):
    return tuple([row[name] for name in fields or row.keys()])


def _dup_host(db, newcontext, oldcontext):
    lookup = {}
    for row in _fetch_table_for_context(db, 'host', oldcontext):
        # id, context, hostname
        row_id, hostname = _row_tuple(row, 'id', 'hostname')
        cursor = db.execute('INSERT INTO host (context, hostname) VALUES(?, ?)',
                            (newcontext, hostname))
        lookup[row_id] = cursor.lastrowid
    return lookup


def _dup_data_source(db, host, newcontext, oldcontext):
    lookup = {}
    for row in _fetch_table_for_context(db, 'data_source', oldcontext):
        # id, context, hostname
        row_id, host_id, actor, phase = _row_tuple(row, 'id', 'host_id', 'actor', 'phase')
        cursor = db.execute('INSERT INTO data_source (context, host_id, actor, phase) VALUES(?, ?, ?, ?)',
                            (newcontext, host[host_id], actor, phase))
        lookup[row_id] = cursor.lastrowid
    return lookup


def _dup_message(db, data_source, newcontext, oldcontext):
    lookup = {}
    for row in _fetch_table_for_context(db, 'message', oldcontext):
        # id, context, data_source_id, stamp, topic, type, message_data_hash
        row_id, data_source_id, stamp, topic, type_, message_data_hash = _row_tuple(
            row, 'id', 'data_source_id', 'stamp', 'topic', 'type', 'message_data_hash')
        cursor = db.execute(
            'INSERT INTO message (context, data_source_id, stamp, topic, type, message_data_hash) '
            ' VALUES(?, ?, ?, ?, ?, ?)',
            (newcontext, data_source[data_source_id], stamp, topic, type_, message_data_hash))
        lookup[row_id] = cursor.lastrowid
    return lookup


def _dup_audit(db, message, data_source, newcontext, oldcontext):
    lookup = {}
    for row in _fetch_table_for_context(db, 'audit', oldcontext):
        # id, context, event, stamp, data_source_id, message_id, data
        row_id, event, stamp, data_source_id, message_id, data = _row_tuple(
            row, 'id', 'event', 'stamp', 'data_source_id', 'message_id', 'data')
        if message_id is not None:
            message_id = message[message_id]

        cursor = db.execute(
            'INSERT INTO audit (context, event, stamp, data_source_id, message_id, data) VALUES(?, ?, ?, ?, ?, ?)',
            (newcontext, event, stamp, data_source[data_source_id], message_id, data))
        lookup[row_id] = cursor.lastrowid
    return lookup


def clone_context(oldcontext, newcontext, use_db=None):
    # Enter transaction - In case of any exception automatic rollback is issued
    # and it is automatically committed if there was no exception
    with get_connection(use_db) as db:
        # First clone host entries
        host = _dup_host(db=db, newcontext=newcontext, oldcontext=oldcontext)
        # Next clone data_source entries and use the lookup table generated by the host duplication
        data_source = _dup_data_source(db=db, host=host, newcontext=newcontext, oldcontext=oldcontext)
        # Next clone message entries and use the lookup table generated by the data_source duplication
        message = _dup_message(db=db, data_source=data_source, newcontext=newcontext, oldcontext=oldcontext)
        # Last clone message entries and use the lookup table generated by the data_source and message duplications
        _dup_audit(db=db, data_source=data_source, message=message, newcontext=newcontext, oldcontext=oldcontext)
