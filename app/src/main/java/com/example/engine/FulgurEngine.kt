package com.example.engine

import kotlin.math.pow

object FulgurConstants {
  const val TOP_K = 5
  const val PAGE_LINES = 40
  const val PAGE_CHARS = 2600
  const val MAX_HITS = 300
  const val MAX_FILE_BYTES = 5 * 1024 * 1024
  const val MIN_QUERY_CHARS = 2
  const val BASE_SCORE_CAP = 500.0
  const val BASE_NORM_SCALE = 100.0
  const val PERSONAL_BASE_FLOOR = 1000.0
  const val PERSONAL_FREQ_WEIGHT = 100.0
  const val HALF_LIFE_DAYS = 14.0

  val SAMPLE_WORDS: List<Pair<String, Int>> = listOf(
    "apple" to 100, "apple watch" to 85, "apple pie" to 60, "application" to 80,
    "apply" to 70, "apricot" to 40, "april" to 55, "apartment" to 50,
    "app store" to 75, "ant" to 20, "anchor" to 15, "android" to 90,
    "angular" to 45, "animal" to 35, "answer" to 30, "antivirus" to 25,
    "banana" to 88, "bank" to 65, "basketball" to 50, "battery" to 52,
    "bike" to 40, "biology" to 33, "bluetooth" to 44, "book" to 70,
    "browser" to 58, "python" to 95, "python tutorial" to 82, "pycharm" to 40,
    "pandas" to 55, "php" to 48, "process" to 45, "processor" to 50,
    "programming" to 85, "protocol" to 42, "c language" to 78, "cache" to 46,
    "computer" to 92, "computer networks" to 66, "cybersecurity" to 72, "coding" to 74,
    "college" to 68, "cricket" to 96, "chrome" to 80, "database" to 77,
    "data structures" to 79, "download" to 60, "diploma" to 62, "ecet" to 83,
    "ecet 2027" to 90, "engineering" to 76, "email" to 70, "flow" to 50,
    "fulgursearch" to 99, "facebook" to 73, "football" to 64, "github" to 81,
    "google" to 100, "gmail" to 78, "game" to 71, "java" to 84,
    "javascript" to 86, "jobs" to 69, "kernel" to 30, "keyboard" to 47,
    "linux" to 73, "laptop" to 67, "mango" to 59, "microprocessor" to 38,
    "mongodb" to 54, "movies" to 87, "mysql" to 56, "network" to 63,
    "notes" to 49, "operating system" to 70, "oracle" to 43, "search engine" to 88,
    "security" to 61, "sql" to 72, "trie" to 28, "typing" to 57,
    "ubuntu" to 52, "youtube" to 98, "weather" to 82, "windows" to 79, "zoom" to 45,
  )

  val STOP_WORDS: Set<String> = setOf(
    "the", "and", "for", "are", "but", "not", "you", "all", "any", "can", "had", "her",
    "was", "one", "our", "out", "has", "have", "this", "that", "with", "from", "they",
    "will", "would", "there", "their", "what", "about", "which", "when", "your", "been",
    "were", "them", "then", "than", "into", "more", "some", "could", "other", "these",
    "also", "its", "his", "how", "who", "may",
  )
}

fun cleanText(s: String): String =
  s.lowercase().trim().split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")

fun boldPrefixLen(rawInput: String): Int {
  val cleaned = cleanText(rawInput)
  if (cleaned.isEmpty()) return 0
  val hasTrailingSpace = rawInput.isNotEmpty() && rawInput.last().isWhitespace() && rawInput.isNotBlank()
  return cleaned.length + if (hasTrailingSpace) 1 else 0
}

class TrieNode {
  val children: HashMap<Char, TrieNode> = HashMap()
  var top: List<Pair<Double, String>> = emptyList()
}

class TopKTrie(private val k: Int = FulgurConstants.TOP_K) {
  private val root = TrieNode()
  private val scores = HashMap<String, Double>()

  fun add(word: String, score: Double = 1.0) {
    val cleaned = cleanText(word)
    if (cleaned.isEmpty()) return
    val total = (scores[cleaned] ?: 0.0) + score
    scores[cleaned] = total
    var node = root
    updateNode(node, cleaned, total)
    for (ch in cleaned) {
      node = node.children.getOrPut(ch) { TrieNode() }
      updateNode(node, cleaned, total)
    }
  }

  private fun updateNode(node: TrieNode, word: String, score: Double) {
    val next = ArrayList<Pair<Double, String>>(node.top.size + 1)
    for (entry in node.top) {
      if (entry.second != word) next.add(entry)
    }
    next.add(score to word)
    next.sortWith(compareByDescending<Pair<Double, String>> { it.first }.thenBy { it.second })
    node.top = if (next.size > k) next.subList(0, k).toList() else next
  }

  fun suggest(prefix: String): List<String> {
    val cleaned = cleanText(prefix)
    if (cleaned.isEmpty()) return emptyList()
    val trailing = if (prefix.isNotEmpty() && prefix.last().isWhitespace() && prefix.isNotBlank()) " " else ""
    var node: TrieNode? = root
    for (ch in cleaned + trailing) {
      node = node?.children?.get(ch) ?: return emptyList()
    }
    return node?.top?.map { it.second } ?: emptyList()
  }
}

data class SearchRecord(val word: String, val count: Int, val lastSearchedAtMs: Long)

class Ranker(private val k: Int = FulgurConstants.TOP_K) {
  private val rawBase = HashMap<String, Double>()
  private val normBase = HashMap<String, Double>()
  private val personalScores = HashMap<String, Double>()
  val trie = TopKTrie(k)

  init {
    for ((w, r) in FulgurConstants.SAMPLE_WORDS) {
      addBaseTerm(w, r.toDouble())
    }
  }

  fun addBaseTerm(word: String, rawWeight: Double) {
    val cleaned = cleanText(word)
    if (cleaned.isEmpty() || rawWeight <= 0.0) return
    val newRaw = (rawBase[cleaned] ?: 0.0) + rawWeight
    rawBase[cleaned] = newRaw
    val oldNorm = normBase[cleaned] ?: 0.0
    val newNorm = FulgurConstants.BASE_SCORE_CAP * (newRaw / (newRaw + FulgurConstants.BASE_NORM_SCALE))
    normBase[cleaned] = newNorm
    val delta = newNorm - oldNorm
    if (delta != 0.0) trie.add(cleaned, delta)
  }

  fun applyDocumentTerms(terms: List<Pair<String, Int>>) {
    for ((w, r) in terms) addBaseTerm(w, r.toDouble())
  }

  fun applyPersonalRecord(rec: SearchRecord, nowMs: Long = System.currentTimeMillis()) {
    val cleaned = cleanText(rec.word)
    if (cleaned.length < FulgurConstants.MIN_QUERY_CHARS || rec.count <= 0) return
    val ageDays = ((nowMs - rec.lastSearchedAtMs).coerceAtLeast(0L)) / 86_400_000.0
    val decay = 0.5 + 0.5 * (0.5.pow(ageDays / FulgurConstants.HALF_LIFE_DAYS))
    val newPersonal = FulgurConstants.PERSONAL_BASE_FLOOR +
      rec.count * FulgurConstants.PERSONAL_FREQ_WEIGHT * decay
    val oldPersonal = personalScores[cleaned] ?: 0.0
    personalScores[cleaned] = newPersonal
    val delta = newPersonal - oldPersonal
    if (delta != 0.0) trie.add(cleaned, delta)
  }
}

data class LearnedResult(
  val detectedMode: String,
  val effectiveMode: String,
  val terms: List<Pair<String, Int>>,
)

object FileLearner {
  private val proseTokenRe = Regex("[\\p{L}\\p{N}][\\p{L}\\p{N}'’-]*")

  fun decodeBytes(raw: ByteArray): String {
    if (raw.size > FulgurConstants.MAX_FILE_BYTES) {
      throw IllegalArgumentException("File exceeds the 5 MB size limit.")
    }
    if (raw.isEmpty()) return ""
    val hasUtf16Bom = raw.size >= 2 && (
      (raw[0] == 0xFF.toByte() && raw[1] == 0xFE.toByte()) ||
        (raw[0] == 0xFE.toByte() && raw[1] == 0xFF.toByte())
      )
    if (!hasUtf16Bom && raw.any { it == 0.toByte() }) {
      throw IllegalArgumentException("Binary files are not supported (NUL bytes detected).")
    }

    val text = when {
      hasUtf16Bom -> raw.toString(Charsets.UTF_16)
      raw.size >= 3 && raw[0] == 0xEF.toByte() && raw[1] == 0xBB.toByte() && raw[2] == 0xBF.toByte() ->
        raw.copyOfRange(3, raw.size).toString(Charsets.UTF_8)
      else -> runCatching {
        Charsets.UTF_8.newDecoder().decode(java.nio.ByteBuffer.wrap(raw)).toString()
      }.getOrElse {
        runCatching {
          java.nio.charset.Charset.forName("windows-1252").newDecoder()
            .decode(java.nio.ByteBuffer.wrap(raw)).toString()
        }.getOrElse { raw.toString(Charsets.ISO_8859_1) }
      }
    }.trimStart('\uFEFF')

    val ctrlCount = text.count { ch ->
      (ch.code < 32 && ch != '\n' && ch != '\r' && ch != '\t') || ch.code == 127
    }
    if (text.isNotEmpty() && ctrlCount.toDouble() / text.length > 0.10) {
      throw IllegalArgumentException("Binary files are not supported (high control-character ratio).")
    }
    return text
  }

  fun learn(text: String, filename: String, modeOverride: String = "auto"): LearnedResult {
    val lines = text.lines().map { it.trim() }.filter { it.isNotEmpty() && !it.startsWith("#") }
    val isCsv = filename.lowercase().endsWith(".csv")
    val detected = if (isCsv || lines.isEmpty()) {
      "wordlist"
    } else {
      val short = lines.count { it.split(Regex("\\s+")).size <= 6 }
      if (short.toDouble() / lines.size >= 0.80) "wordlist" else "prose"
    }
    val effective = if (modeOverride == "wordlist" || modeOverride == "prose") modeOverride else detected

    val terms: List<Pair<String, Int>> = when {
      effective == "prose" -> {
        val counts = HashMap<String, Int>()
        val joined = lines.joinToString("\n").lowercase()
        for (m in proseTokenRe.findAll(joined)) {
          val w = m.value
          if (w.length >= 3 && w !in FulgurConstants.STOP_WORDS) {
            counts[w] = (counts[w] ?: 0) + 1
          }
        }
        counts.entries.sortedByDescending { it.value }.take(5000).map { it.key to it.value }
      }
      isCsv -> {
        lines.mapNotNull { line ->
          val cells = parseCsvLine(line)
          val first = cleanText(cells.firstOrNull().orEmpty())
          if (first.isEmpty()) return@mapNotNull null
          val rank = cells.getOrNull(1)?.trim()?.toIntOrNull()?.coerceAtLeast(1) ?: 1
          first to rank
        }
      }
      else -> {
        lines.mapNotNull { line ->
          val commaIdx = line.lastIndexOf(',')
          var word = line
          var rank = 1
          if (commaIdx > 0) {
            val suffix = line.substring(commaIdx + 1).trim()
            val parsed = suffix.toIntOrNull()
            if (parsed != null && suffix.all { it.isDigit() }) {
              word = line.substring(0, commaIdx)
              rank = parsed.coerceAtLeast(1)
            }
          }
          val cleaned = cleanText(word)
          if (cleaned.isEmpty()) null else cleaned to rank
        }
      }
    }
    return LearnedResult(detectedMode = detected, effectiveMode = effective, terms = terms)
  }

  private fun parseCsvLine(line: String): List<String> {
    val out = ArrayList<String>()
    val cur = StringBuilder()
    var inQuotes = false
    var i = 0
    while (i < line.length) {
      val ch = line[i]
      if (ch == '"') {
        if (inQuotes && i + 1 < line.length && line[i + 1] == '"') {
          cur.append('"')
          i++
        } else {
          inQuotes = !inQuotes
        }
      } else if (ch == ',' && !inQuotes) {
        out.add(cur.toString())
        cur.clear()
      } else {
        cur.append(ch)
      }
      i++
    }
    out.add(cur.toString())
    return out
  }
}

data class PageLine(val number: Int, val text: String)
data class DocPage(val number: Int, val lines: List<PageLine>)

object Paginator {
  fun paginate(text: String): List<DocPage> {
    val rawLines = text.split(Regex("\\r?\\n"))
    val pages = ArrayList<DocPage>()
    var cur = ArrayList<PageLine>()
    var chars = 0
    rawLines.forEachIndexed { idx, lineText ->
      cur.add(PageLine(idx + 1, lineText))
      chars += lineText.length
      if (cur.size >= FulgurConstants.PAGE_LINES || chars >= FulgurConstants.PAGE_CHARS) {
        pages.add(DocPage(pages.size + 1, cur))
        cur = ArrayList()
        chars = 0
      }
    }
    if (cur.isNotEmpty()) pages.add(DocPage(pages.size + 1, cur))
    if (pages.isEmpty()) pages.add(DocPage(1, listOf(PageLine(1, ""))))
    return pages
  }
}

data class MatchHit(
  val doc: String,
  val k: Int,
  val page: Int,
  val line: Int,
  val text: String,
  val idx: Int,
  val len: Int,
)

data class LineSpan(val k: Int, val start: Int, val end: Int)

data class MatchResult(
  val query: String,
  val hits: List<MatchHit>,
  val fileCounts: Map<String, Int>,
  val totalMatches: Int,
  val isCapped: Boolean,
  val lineSpans: Map<Triple<String, Int, Int>, List<LineSpan>>,
)

object Matcher {
  fun findMatches(
    docsPages: List<Pair<String, List<DocPage>>>,
    query: String,
    matchInsideWords: Boolean,
  ): MatchResult {
    val normalized = cleanText(query)
    if (normalized.length < FulgurConstants.MIN_QUERY_CHARS) {
      return MatchResult(normalized, emptyList(), emptyMap(), 0, false, emptyMap())
    }
    val words = normalized.split(" ").filter { it.isNotEmpty() }.map { Regex.escape(it) }
    if (words.isEmpty()) {
      return MatchResult(normalized, emptyList(), emptyMap(), 0, false, emptyMap())
    }
    val body = words.joinToString("\\s+")
    val patternStr = if (matchInsideWords) body else "(?<![\\p{L}\\p{N}])$body"
    val regex = Regex(patternStr, RegexOption.IGNORE_CASE)

    val hits = ArrayList<MatchHit>()
    val counts = HashMap<String, Int>()
    val spans = HashMap<Triple<String, Int, Int>, MutableList<LineSpan>>()
    var totalMatches = 0
    var isCapped = false

    for ((docName, pages) in docsPages) {
      var docK = 0
      for (page in pages) {
        val lines = page.lines
        if (lines.isEmpty()) continue
        val pageText = lines.joinToString("\n") { it.text }
        val offsets = ArrayList<Pair<Int, Int>>(lines.size)
        var pos = 0
        for (l in lines) {
          val end = pos + l.text.length
          offsets.add(pos to end)
          pos = end + 1
        }
        var lineIdx = 0
        for (m in regex.findAll(pageText)) {
          totalMatches++
          counts[docName] = (counts[docName] ?: 0) + 1
          if (hits.size >= FulgurConstants.MAX_HITS) {
            isCapped = true
            continue
          }
          val mStart = m.range.first
          val mEnd = m.range.last + 1
          while (lineIdx < lines.size - 1 && offsets[lineIdx].second < mStart) {
            lineIdx++
          }
          val (startOff, startEnd) = offsets[lineIdx]
          val startLine = lines[lineIdx]
          val relStart = (mStart - startOff).coerceAtLeast(0)
          val snippetText: String
          val hitLen: Int
          if (mEnd > startEnd && lineIdx + 1 < lines.size) {
            val parts = ArrayList<String>()
            parts.add(startLine.text)
            var scan = lineIdx + 1
            while (scan < lines.size && offsets[scan].first < mEnd) {
              parts.add(lines[scan].text)
              scan++
            }
            snippetText = parts.joinToString(" ")
            hitLen = m.value.length
          } else {
            snippetText = startLine.text
            hitLen = (minOf(mEnd, startEnd) - mStart).coerceAtLeast(1)
          }
          hits.add(MatchHit(docName, docK, page.number, startLine.number, snippetText, relStart, hitLen))

          var spanIdx = lineIdx
          while (spanIdx < lines.size) {
            val (lStart, lEnd) = offsets[spanIdx]
            if (lStart >= mEnd) break
            val segStart = maxOf(0, mStart - lStart)
            val segEnd = minOf(lEnd - lStart, mEnd - lStart)
            if (segEnd > segStart) {
              val key = Triple(docName, page.number, lines[spanIdx].number)
              spans.getOrPut(key) { ArrayList() }.add(LineSpan(docK, segStart, segEnd))
            }
            spanIdx++
          }
          docK++
        }
      }
    }
    return MatchResult(normalized, hits, counts, totalMatches, isCapped, spans)
  }
}
