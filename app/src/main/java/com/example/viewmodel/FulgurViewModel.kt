package com.example.viewmodel

import android.app.Application
import android.net.Uri
import android.provider.OpenableColumns
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.engine.DocPage
import com.example.engine.FileLearner
import com.example.engine.FulgurConstants
import com.example.engine.MatchResult
import com.example.engine.Matcher
import com.example.engine.Paginator
import com.example.engine.Ranker
import com.example.engine.SearchRecord
import com.example.engine.cleanText
import com.example.storage.FulgurDatabase
import com.example.storage.StorageSnapshot
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class DocumentState(
  val name: String,
  val text: String,
  val detectedMode: String,
  val modeOverride: String,
  val effectiveMode: String,
  val pages: List<DocPage>,
  val terms: List<Pair<String, Int>>,
)

data class DuplicateCandidate(
  val originalName: String,
  val suggestedAltName: String,
  val bytes: ByteArray,
)

data class FulgurUiState(
  val rawQuery: String = "",
  val suggestions: List<String> = emptyList(),
  val activeSuggestionIndex: Int = -1,
  val statusTiming: String = "",
  val resultHeading: String = "",
  val resultBody: String = "",
  val docs: List<DocumentState> = emptyList(),
  val activeDocName: String? = null,
  val activeSearchQuery: String = "",
  val matchResult: MatchResult? = null,
  val currentHitIndex: Int = -1,
  val matchInsideWords: Boolean = false,
  val searches: List<SearchRecord> = emptyList(),
  val isIndexing: Boolean = false,
  val isMatching: Boolean = false,
  val warningMessage: String? = null,
  val infoNote: String = "",
  val duplicatePrompt: DuplicateCandidate? = null,
  val showUndoResetSnackbar: Boolean = false,
)

class FulgurViewModel(application: Application) : AndroidViewModel(application) {
  private val db = FulgurDatabase(application)
  private var ranker = Ranker()

  private val _uiState = MutableStateFlow(FulgurUiState())
  val uiState: StateFlow<FulgurUiState> = _uiState.asStateFlow()

  private val pendingFiles = ArrayDeque<Pair<String, ByteArray>>()
  private var undoSnapshot: StorageSnapshot? = null
  private var purgeJob: Job? = null

  init {
    loadInitial()
  }

  private fun loadInitial() {
    viewModelScope.launch {
      _uiState.update { it.copy(isIndexing = true) }
      val result = withContext(Dispatchers.IO) {
        runCatching {
          val storedDocs = db.loadDocuments()
          val searches = db.loadSearches()
          val nextRanker = Ranker()
          val docStates = storedDocs.map { d ->
            val learned = FileLearner.learn(d.content, d.name, d.modeOverride)
            val pages = Paginator.paginate(d.content)
            nextRanker.applyDocumentTerms(learned.terms)
            DocumentState(d.name, d.content, learned.detectedMode, d.modeOverride, learned.effectiveMode, pages, learned.terms)
          }
          val now = System.currentTimeMillis()
          searches.forEach { nextRanker.applyPersonalRecord(it, now) }
          Triple(docStates, searches, nextRanker)
        }
      }
      result.onSuccess { (docs, searches, nextRanker) ->
        ranker = nextRanker
        _uiState.update {
          it.copy(
            docs = docs,
            activeDocName = docs.firstOrNull()?.name,
            searches = searches,
            isIndexing = false,
          )
        }
      }.onFailure { err ->
        _uiState.update {
          it.copy(isIndexing = false, warningMessage = "Could not load local SQLite store: ${err.message}")
        }
      }
    }
  }

  fun onQueryChanged(raw: String) {
    if (raw.isBlank()) {
      _uiState.update {
        it.copy(rawQuery = raw, suggestions = emptyList(), activeSuggestionIndex = -1, statusTiming = "")
      }
      return
    }
    val t0 = System.nanoTime()
    val suggestions = ranker.trie.suggest(raw)
    val ms = (System.nanoTime() - t0) / 1_000_000.0
    _uiState.update {
      it.copy(
        rawQuery = raw,
        suggestions = suggestions,
        activeSuggestionIndex = -1,
        statusTiming = if (suggestions.isNotEmpty()) "${suggestions.size} suggestion(s) in ${"%.3f".format(ms)} ms" else "",
      )
    }
  }

  fun completeWith(word: String) {
    onQueryChanged(word)
  }

  fun dismissDropdown() {
    _uiState.update { it.copy(suggestions = emptyList(), activeSuggestionIndex = -1, statusTiming = "") }
  }

  fun doSearch(rawText: String) {
    val cleaned = cleanText(rawText)
    if (cleaned.isEmpty()) return
    _uiState.update { it.copy(rawQuery = "", suggestions = emptyList(), activeSuggestionIndex = -1, statusTiming = "") }

    if (cleaned.length < FulgurConstants.MIN_QUERY_CHARS) {
      _uiState.update {
        it.copy(
          activeSearchQuery = "",
          matchResult = null,
          currentHitIndex = -1,
          resultHeading = "Searched: $cleaned",
          resultBody = "Queries under 2 characters are ignored for ranking and highlighting.",
        )
      }
      return
    }

    viewModelScope.launch {
      val saveRes = withContext(Dispatchers.IO) { runCatching { db.recordSearch(cleaned) } }
      val rec = saveRes.getOrNull()
      val savedOk = saveRes.isSuccess && rec != null
      if (rec != null) {
        ranker.applyPersonalRecord(rec)
        _uiState.update { state ->
          val updated = state.searches.filterNot { it.word == rec.word } + rec
          state.copy(searches = updated)
        }
      } else {
        _uiState.update { it.copy(warningMessage = "Storage error: could not save '$cleaned'.") }
      }

      val docs = _uiState.value.docs
      val inside = _uiState.value.matchInsideWords
      _uiState.update { it.copy(activeSearchQuery = cleaned, isMatching = docs.isNotEmpty()) }

      val matchResult = if (docs.isEmpty()) {
        null
      } else {
        withContext(Dispatchers.Default) {
          Matcher.findMatches(docs.map { it.name to it.pages }, cleaned, inside)
        }
      }

      val countText = if (savedOk && rec != null) {
        "Rank updated (+1). Searched ${rec.count} time(s) so far."
      } else {
        "Could not save search to local storage."
      }
      val tail = when {
        docs.isEmpty() -> "Add a file to see where it appears."
        matchResult != null && matchResult.hits.isNotEmpty() -> {
          val fileCount = matchResult.hits.map { it.doc }.toSet().size
          "Found in $fileCount file(s). Showing the first match below."
        }
        else -> "Not found in your files."
      }

      _uiState.update { state ->
        state.copy(
          matchResult = matchResult,
          currentHitIndex = if (matchResult?.hits?.isNotEmpty() == true) 0 else -1,
          activeDocName = matchResult?.hits?.firstOrNull()?.doc ?: state.activeDocName,
          isMatching = false,
          resultHeading = "Searched: $cleaned",
          resultBody = "$countText $tail",
        )
      }
    }
  }

  fun clearHighlight() {
    _uiState.update {
      it.copy(
        activeSearchQuery = "",
        matchResult = null,
        currentHitIndex = -1,
        resultHeading = "",
        resultBody = "",
      )
    }
  }

  fun selectHit(index: Int) {
    val mr = _uiState.value.matchResult ?: return
    if (mr.hits.isEmpty()) return
    val idx = ((index % mr.hits.size) + mr.hits.size) % mr.hits.size
    val hit = mr.hits[idx]
    _uiState.update { it.copy(currentHitIndex = idx, activeDocName = hit.doc) }
  }

  fun selectTab(name: String) {
    _uiState.update { it.copy(activeDocName = name) }
  }

  fun toggleInsideWords(enabled: Boolean) {
    _uiState.update { it.copy(matchInsideWords = enabled) }
    val q = _uiState.value.activeSearchQuery
    val docs = _uiState.value.docs
    if (q.isNotEmpty() && docs.isNotEmpty()) {
      viewModelScope.launch {
        _uiState.update { it.copy(isMatching = true) }
        val mr = withContext(Dispatchers.Default) {
          Matcher.findMatches(docs.map { it.name to it.pages }, q, enabled)
        }
        _uiState.update {
          it.copy(
            matchResult = mr,
            currentHitIndex = if (mr.hits.isNotEmpty()) 0 else -1,
            activeDocName = mr.hits.firstOrNull()?.doc ?: it.activeDocName,
            isMatching = false,
          )
        }
      }
    }
  }

  fun toggleDocMode(name: String) {
    val current = _uiState.value.docs.find { it.name == name } ?: return
    val nextMode = if (current.effectiveMode == "wordlist") "prose" else "wordlist"
    viewModelScope.launch {
      val res = withContext(Dispatchers.IO) {
        runCatching {
          db.updateDocMode(name, nextMode)
          val learned = FileLearner.learn(current.text, current.name, nextMode)
          current.copy(modeOverride = nextMode, effectiveMode = learned.effectiveMode, terms = learned.terms)
        }
      }
      res.onSuccess { updatedDoc ->
        val docs = _uiState.value.docs.map { if (it.name == name) updatedDoc else it }
        rebuildTrie(docs, _uiState.value.searches)
        _uiState.update { it.copy(docs = docs) }
      }.onFailure { err ->
        _uiState.update { it.copy(warningMessage = "Failed to update mode: ${err.message}") }
      }
    }
  }

  fun removeDoc(name: String) {
    viewModelScope.launch {
      val res = withContext(Dispatchers.IO) { runCatching { db.deleteDocument(name) } }
      res.onFailure { err ->
        _uiState.update { it.copy(warningMessage = "Could not delete '$name': ${err.message}") }
        return@launch
      }
      val docs = _uiState.value.docs.filterNot { it.name == name }
      rebuildTrie(docs, _uiState.value.searches)
      _uiState.update { state ->
        val nextActive = if (state.activeDocName == name) docs.firstOrNull()?.name else state.activeDocName
        state.copy(docs = docs, activeDocName = nextActive)
      }
      val activeQ = _uiState.value.activeSearchQuery
      if (activeQ.isNotEmpty()) toggleInsideWords(_uiState.value.matchInsideWords)
    }
  }

  fun deleteSearch(word: String) {
    viewModelScope.launch {
      withContext(Dispatchers.IO) { db.deleteSearch(word) }
      val nextSearches = _uiState.value.searches.filterNot { it.word == word }
      rebuildTrie(_uiState.value.docs, nextSearches)
      _uiState.update { it.copy(searches = nextSearches) }
      if (_uiState.value.rawQuery.isNotBlank()) onQueryChanged(_uiState.value.rawQuery)
    }
  }

  fun startUndoableReset() {
    purgeJob?.cancel()
    viewModelScope.launch {
      undoSnapshot = withContext(Dispatchers.IO) { db.snapshot() }
      ranker = Ranker()
      _uiState.update {
        it.copy(
          docs = emptyList(),
          searches = emptyList(),
          activeDocName = null,
          activeSearchQuery = "",
          matchResult = null,
          currentHitIndex = -1,
          resultHeading = "",
          resultBody = "",
          showUndoResetSnackbar = true,
        )
      }
      purgeJob = viewModelScope.launch {
        delay(8000L)
        if (undoSnapshot != null) {
          undoSnapshot = null
          withContext(Dispatchers.IO) { db.purgeAll() }
          _uiState.update { it.copy(showUndoResetSnackbar = false) }
        }
      }
    }
  }

  fun undoReset() {
    purgeJob?.cancel()
    val snap = undoSnapshot ?: return
    undoSnapshot = null
    viewModelScope.launch {
      withContext(Dispatchers.IO) { db.restore(snap) }
      _uiState.update { it.copy(showUndoResetSnackbar = false) }
      loadInitial()
    }
  }

  fun ingestPickedUris(uris: List<Uri>) {
    if (uris.isEmpty()) return
    viewModelScope.launch {
      val errors = ArrayList<String>()
      val resolver = getApplication<Application>().contentResolver
      withContext(Dispatchers.IO) {
        for (uri in uris) {
          val name = resolveFileName(uri)
          val extOk = name.lowercase().let { it.endsWith(".txt") || it.endsWith(".md") || it.endsWith(".csv") }
          if (!extOk) {
            errors.add("$name: unsupported file type (use .txt, .md, or .csv).")
            continue
          }
          val bytes = runCatching { resolver.openInputStream(uri)?.use { it.readBytes() } }.getOrNull()
          if (bytes == null) {
            errors.add("$name: could not read file.")
          } else {
            pendingFiles.addLast(name to bytes)
          }
        }
      }
      if (errors.isNotEmpty()) {
        _uiState.update { it.copy(warningMessage = errors.joinToString(" • ")) }
      }
      processNextPendingFile()
    }
  }

  private fun processNextPendingFile() {
    if (pendingFiles.isEmpty()) return
    val (name, bytes) = pendingFiles.first()
    val existingNames = _uiState.value.docs.map { it.name }.toSet()
    if (name in existingNames) {
      val alt = uniqueAltName(name, existingNames)
      _uiState.update { it.copy(duplicatePrompt = DuplicateCandidate(name, alt, bytes)) }
      return
    }
    pendingFiles.removeFirst()
    saveAndIndexFile(name, bytes)
  }

  fun resolveDuplicate(replace: Boolean, cancel: Boolean) {
    val dup = _uiState.value.duplicatePrompt ?: return
    _uiState.update { it.copy(duplicatePrompt = null) }
    if (pendingFiles.isNotEmpty()) pendingFiles.removeFirst()
    if (!cancel) {
      val target = if (replace) dup.originalName else dup.suggestedAltName
      saveAndIndexFile(target, dup.bytes)
    } else {
      processNextPendingFile()
    }
  }

  private fun saveAndIndexFile(name: String, bytes: ByteArray) {
    viewModelScope.launch {
      _uiState.update { it.copy(isIndexing = true) }
      val outcome = withContext(Dispatchers.Default) {
        runCatching {
          val text = FileLearner.decodeBytes(bytes)
          val learned = FileLearner.learn(text, name, "auto")
          val pages = Paginator.paginate(text)
          withContext(Dispatchers.IO) {
            db.upsertDocument(name, text, learned.detectedMode, "auto")
          }
          DocumentState(name, text, learned.detectedMode, "auto", learned.effectiveMode, pages, learned.terms)
        }
      }
      outcome.onSuccess { doc ->
        val existingIdx = _uiState.value.docs.indexOfFirst { it.name == doc.name }
        val nextDocs = if (existingIdx >= 0) {
          _uiState.value.docs.toMutableList().apply { set(existingIdx, doc) }
        } else {
          _uiState.value.docs + doc
        }
        if (existingIdx >= 0) {
          rebuildTrie(nextDocs, _uiState.value.searches)
        } else {
          ranker.applyDocumentTerms(doc.terms)
        }
        _uiState.update {
          it.copy(
            docs = nextDocs,
            activeDocName = doc.name,
            isIndexing = false,
            infoNote = "Loaded ${doc.name}.",
          )
        }
        if (_uiState.value.rawQuery.isNotBlank()) onQueryChanged(_uiState.value.rawQuery)
      }.onFailure { err ->
        _uiState.update {
          it.copy(isIndexing = false, warningMessage = "$name: ${err.message}")
        }
      }
      processNextPendingFile()
    }
  }

  fun dismissWarning() {
    _uiState.update { it.copy(warningMessage = null) }
  }

  private fun rebuildTrie(docs: List<DocumentState>, searches: List<SearchRecord>) {
    val next = Ranker()
    docs.forEach { next.applyDocumentTerms(it.terms) }
    val now = System.currentTimeMillis()
    searches.forEach { next.applyPersonalRecord(it, now) }
    ranker = next
  }

  private fun uniqueAltName(name: String, existing: Set<String>): String {
    val dot = name.lastIndexOf('.')
    val stem = if (dot > 0) name.substring(0, dot) else name
    val ext = if (dot > 0) name.substring(dot) else ""
    var n = 2
    while (true) {
      val candidate = "$stem ($n)$ext"
      if (candidate !in existing) return candidate
      n++
    }
  }

  private fun resolveFileName(uri: Uri): String {
    getApplication<Application>().contentResolver.query(uri, null, null, null, null)?.use { c ->
      val idx = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
      if (idx >= 0 && c.moveToFirst()) {
        return c.getString(idx) ?: "document.txt"
      }
    }
    return uri.lastPathSegment?.substringAfterLast('/') ?: "document.txt"
  }
}
