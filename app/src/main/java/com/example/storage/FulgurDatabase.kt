package com.example.storage

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import com.example.engine.SearchRecord

data class StoredDocument(
  val name: String,
  val content: String,
  val detectedMode: String,
  val modeOverride: String,
  val updatedAtMs: Long,
)

data class StorageSnapshot(
  val documents: List<StoredDocument>,
  val searches: List<SearchRecord>,
)

class FulgurDatabase(context: Context) :
  SQLiteOpenHelper(context.applicationContext, "fulgur_search.db", null, 1) {

  override fun onConfigure(db: SQLiteDatabase) {
    super.onConfigure(db)
    db.enableWriteAheadLogging()
  }

  override fun onCreate(db: SQLiteDatabase) {
    db.execSQL(
      """
      CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        content TEXT NOT NULL,
        detected_mode TEXT NOT NULL,
        mode_override TEXT NOT NULL DEFAULT 'auto',
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
      );
      """.trimIndent()
    )
    db.execSQL(
      """
      CREATE TABLE IF NOT EXISTS searches (
        word TEXT PRIMARY KEY,
        count INTEGER NOT NULL,
        last_searched_at INTEGER NOT NULL
      );
      """.trimIndent()
    )
    db.execSQL(
      """
      CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
      );
      """.trimIndent()
    )
  }

  override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) = Unit

  fun loadDocuments(): List<StoredDocument> {
    val list = ArrayList<StoredDocument>()
    readableDatabase.rawQuery(
      "SELECT name, content, detected_mode, mode_override, updated_at FROM documents ORDER BY id ASC",
      null,
    ).use { c ->
      while (c.moveToNext()) {
        list.add(
          StoredDocument(
            name = c.getString(0),
            content = c.getString(1),
            detectedMode = c.getString(2),
            modeOverride = c.getString(3),
            updatedAtMs = c.getLong(4),
          )
        )
      }
    }
    return list
  }

  fun loadSearches(): List<SearchRecord> {
    val list = ArrayList<SearchRecord>()
    readableDatabase.rawQuery(
      "SELECT word, count, last_searched_at FROM searches ORDER BY count DESC, last_searched_at DESC",
      null,
    ).use { c ->
      while (c.moveToNext()) {
        list.add(SearchRecord(c.getString(0), c.getInt(1), c.getLong(2)))
      }
    }
    return list
  }

  fun upsertDocument(name: String, content: String, detectedMode: String, modeOverride: String) {
    val now = System.currentTimeMillis()
    val db = writableDatabase
    db.beginTransaction()
    try {
      val cv = ContentValues().apply {
        put("name", name)
        put("content", content)
        put("detected_mode", detectedMode)
        put("mode_override", modeOverride)
        put("created_at", now)
        put("updated_at", now)
      }
      db.insertWithOnConflict("documents", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
      db.setTransactionSuccessful()
    } finally {
      db.endTransaction()
    }
  }

  fun updateDocMode(name: String, modeOverride: String) {
    val db = writableDatabase
    db.beginTransaction()
    try {
      val cv = ContentValues().apply {
        put("mode_override", modeOverride)
        put("updated_at", System.currentTimeMillis())
      }
      db.update("documents", cv, "name = ?", arrayOf(name))
      db.setTransactionSuccessful()
    } finally {
      db.endTransaction()
    }
  }

  fun deleteDocument(name: String) {
    val db = writableDatabase
    db.beginTransaction()
    try {
      db.delete("documents", "name = ?", arrayOf(name))
      db.setTransactionSuccessful()
    } finally {
      db.endTransaction()
    }
  }

  fun recordSearch(word: String): SearchRecord {
    val now = System.currentTimeMillis()
    val db = writableDatabase
    db.beginTransaction()
    try {
      db.execSQL(
        """
        INSERT INTO searches (word, count, last_searched_at) VALUES (?, 1, ?)
        ON CONFLICT(word) DO UPDATE SET
          count = searches.count + 1,
          last_searched_at = excluded.last_searched_at
        """.trimIndent(),
        arrayOf<Any>(word, now),
      )
      val count = db.rawQuery("SELECT count FROM searches WHERE word = ?", arrayOf(word)).use { c ->
        if (c.moveToFirst()) c.getInt(0) else 1
      }
      db.setTransactionSuccessful()
      return SearchRecord(word, count, now)
    } finally {
      db.endTransaction()
    }
  }

  fun deleteSearch(word: String) {
    val db = writableDatabase
    db.beginTransaction()
    try {
      db.delete("searches", "word = ?", arrayOf(word))
      db.setTransactionSuccessful()
    } finally {
      db.endTransaction()
    }
  }

  fun snapshot(): StorageSnapshot = StorageSnapshot(loadDocuments(), loadSearches())

  fun purgeAll() {
    val db = writableDatabase
    db.beginTransaction()
    try {
      db.delete("documents", null, null)
      db.delete("searches", null, null)
      db.setTransactionSuccessful()
    } finally {
      db.endTransaction()
    }
  }

  fun restore(snapshot: StorageSnapshot) {
    val db = writableDatabase
    db.beginTransaction()
    try {
      db.delete("documents", null, null)
      db.delete("searches", null, null)
      for (d in snapshot.documents) {
        val cv = ContentValues().apply {
          put("name", d.name)
          put("content", d.content)
          put("detected_mode", d.detectedMode)
          put("mode_override", d.modeOverride)
          put("created_at", d.updatedAtMs)
          put("updated_at", d.updatedAtMs)
        }
        db.insert("documents", null, cv)
      }
      for (s in snapshot.searches) {
        val cv = ContentValues().apply {
          put("word", s.word)
          put("count", s.count)
          put("last_searched_at", s.lastSearchedAtMs)
        }
        db.insert("searches", null, cv)
      }
      db.setTransactionSuccessful()
    } finally {
      db.endTransaction()
    }
  }
}
