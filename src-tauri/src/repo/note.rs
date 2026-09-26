use crate::models::Note;
use crate::repo::now;
use rusqlite::{params, Connection, Result};

/// 正常笔记的公共过滤条件：排除已移入垃圾箱的条目
const ALIVE_WHERE: &str = "deleted_at IS NULL";

pub fn create(conn: &Connection, title: &str) -> Result<Note> {
    let ts = now();
    conn.execute(
        "INSERT INTO notes (title, created_at, updated_at) VALUES (?1, ?2, ?2)",
        params![title, ts],
    )?;
    get(conn, conn.last_insert_rowid())
}

pub fn get(conn: &Connection, id: i64) -> Result<Note> {
    conn.query_row(
        "SELECT id, title, content, created_at, updated_at, deleted_at FROM notes WHERE id = ?1",
        params![id],
        row_to_note,
    )
}

pub fn list(conn: &Connection) -> Result<Vec<Note>> {
    let mut stmt = conn.prepare(&format!(
        "SELECT id, title, content, created_at, updated_at, deleted_at FROM notes
         WHERE {ALIVE_WHERE} ORDER BY updated_at DESC, id DESC"
    ))?;
    let rows = stmt.query_map([], row_to_note)?;
    rows.collect()
}

/// 笔记列表（仅元信息，不拉 content）：用于外部保存速记后主窗口刷新列表，
/// 避免每次刷新都全量读取正文，数据量大时省内存省 IO。
pub fn list_meta(conn: &Connection) -> Result<Vec<Note>> {
    let mut stmt = conn.prepare(&format!(
        "SELECT id, title, '', created_at, updated_at, deleted_at FROM notes
         WHERE {ALIVE_WHERE} ORDER BY updated_at DESC, id DESC"
    ))?;
    let rows = stmt.query_map([], row_to_note)?;
    rows.collect()
}

pub fn update(conn: &Connection, id: i64, title: &str, content: &str) -> Result<Note> {
    let affected = conn.execute(
        "UPDATE notes SET title = ?1, content = ?2, updated_at = ?3 WHERE id = ?4 AND deleted_at IS NULL",
        params![title, content, now(), id],
    )?;
    if affected == 0 {
        // 带 NOT_FOUND 前缀：扩展桥调用方据此与服务器错误区分，不再盲目重试
        return Err(rusqlite::Error::InvalidParameterName(format!(
            "NOT_FOUND: 笔记 {id} 不存在"
        )));
    }
    get(conn, id)
}

/// 移入垃圾箱（软删除）：保留内容与标签关联，可恢复
pub fn soft_delete(conn: &Connection, id: i64) -> Result<()> {
    conn.execute(
        "UPDATE notes SET deleted_at = ?1 WHERE id = ?2 AND deleted_at IS NULL",
        params![now(), id],
    )?;
    Ok(())
}

/// 从垃圾箱恢复
pub fn restore(conn: &Connection, id: i64) -> Result<()> {
    conn.execute(
        "UPDATE notes SET deleted_at = NULL WHERE id = ?1 AND deleted_at IS NOT NULL",
        params![id],
    )?;
    Ok(())
}

/// 彻底删除（硬删除）：note_tags 由外键 ON DELETE CASCADE 自动清理
pub fn purge(conn: &Connection, id: i64) -> Result<()> {
    conn.execute(
        "DELETE FROM notes WHERE id = ?1 AND deleted_at IS NOT NULL",
        params![id],
    )?;
    Ok(())
}

/// 垃圾箱列表：按移入时间倒序
pub fn list_trash(conn: &Connection) -> Result<Vec<Note>> {
    let mut stmt = conn.prepare(
        "SELECT id, title, content, created_at, updated_at, deleted_at FROM notes
         WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC, id DESC",
    )?;
    let rows = stmt.query_map([], row_to_note)?;
    rows.collect()
}

/// 清空垃圾箱
pub fn empty_trash(conn: &Connection) -> Result<usize> {
    conn.execute("DELETE FROM notes WHERE deleted_at IS NOT NULL", [])
}

pub fn search(conn: &Connection, keyword: &str) -> Result<Vec<Note>> {
    let pattern = format!("%{}%", keyword);
    let mut stmt = conn.prepare(&format!(
        "SELECT id, title, content, created_at, updated_at, deleted_at FROM notes
         WHERE ({ALIVE_WHERE}) AND (title LIKE ?1 OR content LIKE ?1)
         ORDER BY updated_at DESC"
    ))?;
    let rows = stmt.query_map(params![pattern], row_to_note)?;
    rows.collect()
}

pub fn row_to_note(row: &rusqlite::Row) -> Result<Note> {
    Ok(Note {
        id: row.get(0)?,
        title: row.get(1)?,
        content: row.get(2)?,
        created_at: row.get(3)?,
        updated_at: row.get(4)?,
        deleted_at: row.get(5)?,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::db::init_in_memory;

    #[test]
    fn create_and_get_note() {
        let conn = init_in_memory().unwrap();
        let n = create(&conn, "待办事项").unwrap();
        assert_eq!(n.title, "待办事项");
        assert_eq!(n.content, "");
        assert!(n.deleted_at.is_none());
    }

    #[test]
    fn list_notes_ordered_by_updated_desc() {
        let conn = init_in_memory().unwrap();
        let a = create(&conn, "A").unwrap();
        let b = create(&conn, "B").unwrap();
        update(&conn, a.id, "A", "updated later").unwrap();
        let list = list(&conn).unwrap();
        assert_eq!(list.iter().map(|n| n.id).collect::<Vec<_>>(), vec![a.id, b.id]);
    }

    #[test]
    fn update_note_title_and_content() {
        let conn = init_in_memory().unwrap();
        let n = create(&conn, "T").unwrap();
        let updated = update(&conn, n.id, "新标题", "这是内容").unwrap();
        assert_eq!(updated.title, "新标题");
        assert_eq!(updated.content, "这是内容");
    }

    #[test]
    fn trash_flow_soft_delete_restore_purge() {
        let conn = init_in_memory().unwrap();
        let a = create(&conn, "甲").unwrap();
        let b = create(&conn, "乙").unwrap();

        // 软删除后：活跃列表看不到，垃圾箱看得到
        soft_delete(&conn, a.id).unwrap();
        assert!(list(&conn).unwrap().iter().all(|n| n.id != a.id));
        let trash = list_trash(&conn).unwrap();
        assert_eq!(trash.iter().map(|n| n.id).collect::<Vec<_>>(), vec![a.id]);
        assert!(trash[0].deleted_at.is_some());
        // 软删除后不可再编辑（update 只作用于活跃笔记）
        assert!(update(&conn, a.id, "改", "改").is_err());

        // 恢复后回到活跃列表
        restore(&conn, a.id).unwrap();
        assert!(list(&conn).unwrap().iter().any(|n| n.id == a.id));
        assert!(list_trash(&conn).unwrap().is_empty());

        // 再删除后彻底删除：物理消失
        soft_delete(&conn, b.id).unwrap();
        purge(&conn, b.id).unwrap();
        assert!(get(&conn, b.id).is_err());
        assert!(list(&conn).unwrap().iter().all(|n| n.id != b.id));
    }

    #[test]
    fn empty_trash_purges_all_deleted() {
        let conn = init_in_memory().unwrap();
        let a = create(&conn, "A").unwrap();
        let b = create(&conn, "B").unwrap();
        soft_delete(&conn, a.id).unwrap();
        soft_delete(&conn, b.id).unwrap();
        assert_eq!(empty_trash(&conn).unwrap(), 2);
        assert!(list_trash(&conn).unwrap().is_empty());
        assert!(list(&conn).unwrap().is_empty());
    }

    #[test]
    fn search_excludes_trashed() {
        let conn = init_in_memory().unwrap();
        let a = create(&conn, "速记_alpha").unwrap();
        create(&conn, "速记_beta").unwrap();
        soft_delete(&conn, a.id).unwrap();
        let hits = search(&conn, "速记").unwrap();
        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].title, "速记_beta");
    }
}
