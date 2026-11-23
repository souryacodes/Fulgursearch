package com.example

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.DisableSelection
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.minimumInteractiveComponentSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.engine.DocPage
import com.example.engine.FulgurConstants
import com.example.engine.LineSpan
import com.example.engine.MatchHit
import com.example.engine.boldPrefixLen
import com.example.ui.theme.LocalFulgurPalette
import com.example.ui.theme.MyApplicationTheme
import com.example.viewmodel.DocumentState
import com.example.viewmodel.FulgurViewModel
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    enableEdgeToEdge()
    setContent {
      MyApplicationTheme {
        FulgurSearchScreen()
      }
    }
  }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FulgurSearchScreen(vm: FulgurViewModel = viewModel()) {
  val state by vm.uiState.collectAsStateWithLifecycle()
  val palette = LocalFulgurPalette.current
  val snackbarHostState = remember { SnackbarHostState() }
  val scope = rememberCoroutineScope()

  var docToRemove by remember { mutableStateOf<String?>(null) }
  var showResetConfirm by remember { mutableStateOf(false) }

  val filePickerLauncher = rememberLauncherForActivityResult(
    contract = ActivityResultContracts.OpenMultipleDocuments(),
  ) { uris ->
    if (uris.isNotEmpty()) vm.ingestPickedUris(uris)
  }

  LaunchedEffect(state.showUndoResetSnackbar) {
    if (state.showUndoResetSnackbar) {
      val res = snackbarHostState.showSnackbar(
        message = "Learned data reset.",
        actionLabel = "Undo",
        duration = SnackbarDuration.Long,
      )
      if (res == SnackbarResult.ActionPerformed) vm.undoReset()
    }
  }

  BackHandler(enabled = state.suggestions.isNotEmpty() || docToRemove != null || showResetConfirm || state.duplicatePrompt != null) {
    when {
      state.suggestions.isNotEmpty() -> vm.dismissDropdown()
      state.duplicatePrompt != null -> vm.resolveDuplicate(replace = false, cancel = true)
      docToRemove != null -> docToRemove = null
      showResetConfirm -> showResetConfirm = false
    }
  }

  Scaffold(
    containerColor = palette.bg,
    contentWindowInsets = WindowInsets.safeDrawing,
    snackbarHost = { SnackbarHost(snackbarHostState) },
  ) { innerPadding ->
    val outerScroll = rememberScrollState()
    val viewerListState = rememberLazyListState()
    var pageInputText by remember { mutableStateOf("1") }

    val activeDoc: DocumentState? = state.docs.find { it.name == state.activeDocName }
    LaunchedEffect(viewerListState.firstVisibleItemIndex, activeDoc?.name) {
      if (activeDoc != null && activeDoc.pages.isNotEmpty()) {
        pageInputText = (viewerListState.firstVisibleItemIndex + 1).toString()
      }
    }
    LaunchedEffect(state.currentHitIndex, state.matchResult) {
      val hit = state.matchResult?.hits?.getOrNull(state.currentHitIndex)
      if (hit != null && hit.doc == activeDoc?.name) {
        viewerListState.animateScrollToItem((hit.page - 1).coerceAtLeast(0))
      }
    }

    Box(
      modifier = Modifier
        .fillMaxSize()
        .padding(innerPadding)
        .imePadding(),
      contentAlignment = Alignment.TopCenter,
    ) {
      Column(
        modifier = Modifier
          .widthIn(max = 760.dp)
          .fillMaxWidth()
          .verticalScroll(outerScroll)
          .padding(horizontal = 16.dp, vertical = 24.dp),
      ) {
        if (state.warningMessage != null) {
          Card(
            colors = CardDefaults.cardColors(containerColor = palette.hitBarBg),
            border = BorderStroke(1.dp, palette.currentMatchOutline),
            shape = RoundedCornerShape(10.dp),
            modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp),
          ) {
            Row(
              modifier = Modifier.padding(12.dp),
              verticalAlignment = Alignment.CenterVertically,
            ) {
              Icon(Icons.Default.Warning, contentDescription = "Warning", tint = palette.currentMatchOutline)
              Spacer(Modifier.width(8.dp))
              Text(state.warningMessage.orEmpty(), color = palette.text, fontSize = 14.sp, modifier = Modifier.weight(1f))
              IconButton(onClick = { vm.dismissWarning() }) {
                Icon(Icons.Default.Close, contentDescription = "Dismiss warning", tint = palette.text)
              }
            }
          }
        }

        // Title & subtitle
        Text(
          text = buildAnnotatedString {
            append("Fulgur ")
            withStyle(SpanStyle(color = palette.primary)) { append("Search") }
          },
          fontSize = 40.sp,
          fontWeight = FontWeight.Bold,
          letterSpacing = (-1).sp,
          color = palette.text,
          textAlign = TextAlign.Center,
          modifier = Modifier.fillMaxWidth(),
        )
        Text(
          text = "Instant search suggestions, ranked",
          fontSize = 15.sp,
          color = palette.muted,
          textAlign = TextAlign.Center,
          modifier = Modifier.fillMaxWidth().padding(top = 6.dp, bottom = 22.dp),
        )

        // Search input + Search button
        Row(
          modifier = Modifier.fillMaxWidth(),
          horizontalArrangement = Arrangement.spacedBy(8.dp),
          verticalAlignment = Alignment.CenterVertically,
        ) {
          OutlinedTextField(
            value = state.rawQuery,
            onValueChange = { vm.onQueryChanged(it) },
            placeholder = { Text("Start typing... (try \"a\")", color = palette.muted, fontSize = 17.sp) },
            singleLine = true,
            textStyle = TextStyle(fontSize = 18.sp, color = palette.text),
            shape = RoundedCornerShape(10.dp),
            colors = OutlinedTextFieldDefaults.colors(
              focusedContainerColor = palette.card,
              unfocusedContainerColor = palette.card,
              focusedBorderColor = palette.primary,
              unfocusedBorderColor = palette.border,
            ),
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { vm.doSearch(state.rawQuery) }),
            modifier = Modifier
              .weight(1f)
              .testTag("search_input"),
          )
          Button(
            onClick = { vm.doSearch(state.rawQuery) },
            shape = RoundedCornerShape(10.dp),
            colors = ButtonDefaults.buttonColors(containerColor = palette.primary),
            contentPadding = PaddingValues(horizontal = 18.dp),
            modifier = Modifier.height(54.dp).testTag("search_button"),
          ) {
            Text("Search", fontSize = 16.sp, color = palette.onPrimary)
          }
        }

        // Suggestions dropdown
        if (state.rawQuery.isNotBlank()) {
          Card(
            colors = CardDefaults.cardColors(containerColor = palette.card),
            shape = RoundedCornerShape(10.dp),
            elevation = CardDefaults.cardElevation(defaultElevation = 3.dp),
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
          ) {
            if (state.suggestions.isEmpty()) {
              Text(
                text = "No suggestions. Press Search to add this word.",
                color = palette.muted,
                fontSize = 15.sp,
                modifier = Modifier.padding(16.dp),
              )
            } else {
              val n = boldPrefixLen(state.rawQuery)
              Column {
                state.suggestions.forEachIndexed { idx, word ->
                  val total = state.suggestions.size
                  Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier
                      .fillMaxWidth()
                      .minimumInteractiveComponentSize()
                      .clickable { vm.doSearch(word) }
                      .semantics { contentDescription = "suggestion ${idx + 1} of $total, $word" }
                      .padding(horizontal = 16.dp, vertical = 10.dp),
                  ) {
                    Text("#${idx + 1}", fontSize = 13.sp, color = palette.muted, modifier = Modifier.width(26.dp))
                    Spacer(Modifier.width(12.dp))
                    Text(
                      text = buildAnnotatedString {
                        withStyle(SpanStyle(color = palette.primary, fontWeight = FontWeight.Bold)) {
                          append(word.take(n))
                        }
                        append(word.drop(n))
                      },
                      fontSize = 17.sp,
                      color = palette.text,
                      maxLines = 1,
                      overflow = TextOverflow.Ellipsis,
                      modifier = Modifier.weight(1f),
                    )
                    TextButton(
                      onClick = { vm.completeWith(word) },
                      modifier = Modifier.minimumInteractiveComponentSize().testTag("complete_btn_$idx"),
                    ) {
                      Text("↖ complete", fontSize = 12.sp, color = palette.muted)
                    }
                  }
                  if (idx < total - 1) HorizontalDivider(color = palette.divider)
                }
              }
            }
          }
        }

        if (state.statusTiming.isNotEmpty()) {
          Text(
            text = state.statusTiming,
            fontSize = 13.sp,
            color = palette.muted,
            modifier = Modifier
              .padding(top = 8.dp, start = 4.dp)
              .semantics { liveRegion = LiveRegionMode.Polite },
          )
        }

        if (state.resultHeading.isNotEmpty()) {
          Card(
            colors = CardDefaults.cardColors(containerColor = palette.card),
            shape = RoundedCornerShape(10.dp),
            elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
            modifier = Modifier
              .fillMaxWidth()
              .padding(top = 12.dp)
              .semantics { liveRegion = LiveRegionMode.Polite },
          ) {
            Column(modifier = Modifier.padding(16.dp)) {
              Text(state.resultHeading, fontSize = 18.sp, fontWeight = FontWeight.Bold, color = palette.text)
              Spacer(Modifier.height(4.dp))
              Text(state.resultBody, fontSize = 15.sp, color = palette.muted)
            }
          }
        }

        // Document Viewer Card
        Card(
          colors = CardDefaults.cardColors(containerColor = palette.card),
          shape = RoundedCornerShape(10.dp),
          elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
          modifier = Modifier.fillMaxWidth().padding(top = 18.dp),
        ) {
          Column {
            // Tabs + Add files
            Row(
              modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 10.dp),
              verticalAlignment = Alignment.CenterVertically,
            ) {
              Row(
                modifier = Modifier.weight(1f).horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically,
              ) {
                if (state.docs.isEmpty()) {
                  Text("No files yet", fontSize = 13.sp, color = palette.muted)
                } else {
                  state.docs.forEach { doc ->
                    val isSelected = doc.name == state.activeDocName
                    val badgeCount = if (state.activeSearchQuery.isNotEmpty()) {
                      state.matchResult?.fileCounts?.get(doc.name) ?: 0
                    } else 0
                    Surface(
                      color = if (isSelected) palette.primary else palette.lightBtn,
                      shape = RoundedCornerShape(8.dp),
                      modifier = Modifier.semantics { selected = isSelected },
                    ) {
                      Row(verticalAlignment = Alignment.CenterVertically) {
                        Row(
                          verticalAlignment = Alignment.CenterVertically,
                          modifier = Modifier
                            .minimumInteractiveComponentSize()
                            .clickable { vm.selectTab(doc.name) }
                            .padding(start = 10.dp, end = 4.dp),
                        ) {
                          Text(
                            doc.name,
                            fontSize = 13.sp,
                            color = if (isSelected) palette.onPrimary else palette.text,
                          )
                          if (badgeCount > 0) {
                            Spacer(Modifier.width(6.dp))
                            Box(
                              modifier = Modifier
                                .clip(RoundedCornerShape(9.dp))
                                .background(palette.highlightBg)
                                .padding(horizontal = 6.dp, vertical = 1.dp),
                            ) {
                              Text(
                                text = if (badgeCount > FulgurConstants.MAX_HITS) "300+" else badgeCount.toString(),
                                fontSize = 11.sp,
                                color = palette.highlightText,
                                fontWeight = FontWeight.Bold,
                              )
                            }
                          }
                        }
                        IconButton(
                          onClick = { docToRemove = doc.name },
                          modifier = Modifier.size(40.dp),
                        ) {
                          Icon(
                            Icons.Default.Close,
                            contentDescription = "Remove ${doc.name}",
                            tint = if (isSelected) palette.onPrimary else palette.text,
                            modifier = Modifier.size(16.dp),
                          )
                        }
                      }
                    }
                  }
                }
              }
              Spacer(Modifier.width(8.dp))
              OutlinedButton(
                onClick = { filePickerLauncher.launch(arrayOf("text/plain", "text/csv", "text/markdown", "text/*")) },
                shape = RoundedCornerShape(10.dp),
                colors = ButtonDefaults.outlinedButtonColors(containerColor = palette.lightBtn),
                border = null,
                modifier = Modifier.height(48.dp).testTag("add_files_button"),
              ) {
                Text("Add files", fontSize = 14.sp, color = palette.text)
              }
            }

            if (activeDoc != null) {
              HorizontalDivider(color = palette.divider)
              Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
              ) {
                val modeLabel = if (activeDoc.effectiveMode == "wordlist") "word list" else "prose"
                val altLabel = if (activeDoc.effectiveMode == "wordlist") "prose" else "word list"
                Text("Learned as: $modeLabel", fontSize = 13.sp, color = palette.muted)
                Spacer(Modifier.width(8.dp))
                TextButton(onClick = { vm.toggleDocMode(activeDoc.name) }) {
                  Text("Switch to $altLabel", fontSize = 13.sp, color = palette.primary)
                }
              }
            }

            // Hit Bar + Hit List
            val mr = state.matchResult
            if (state.activeSearchQuery.isNotEmpty() && mr != null) {
              Column(
                modifier = Modifier
                  .fillMaxWidth()
                  .background(palette.hitBarBg)
                  .border(1.dp, palette.hitBarBorder)
                  .padding(12.dp),
              ) {
                Row(
                  verticalAlignment = Alignment.CenterVertically,
                  modifier = Modifier.fillMaxWidth(),
                ) {
                  val hitSummary = when {
                    mr.hits.isEmpty() -> "No match for “${mr.query}” in your files."
                    mr.isCapped -> {
                      val curHit = mr.hits.getOrNull(state.currentHitIndex) ?: mr.hits.first()
                      "300+ matches (showing first 300) — match ${state.currentHitIndex + 1} of ${mr.hits.size} (${curHit.doc}, page ${curHit.page}, line ${curHit.line})"
                    }
                    else -> {
                      val curHit = mr.hits.getOrNull(state.currentHitIndex) ?: mr.hits.first()
                      "“${mr.query}”: match ${state.currentHitIndex + 1} of ${mr.hits.size} (${curHit.doc}, page ${curHit.page}, line ${curHit.line})"
                    }
                  }
                  Text(hitSummary, fontSize = 14.sp, color = palette.text, modifier = Modifier.weight(1f))
                }
                Spacer(Modifier.height(6.dp))
                FlowRow(
                  horizontalArrangement = Arrangement.spacedBy(8.dp),
                  verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                  OutlinedButton(
                    onClick = { vm.selectHit(state.currentHitIndex - 1) },
                    enabled = mr.hits.size >= 2,
                    colors = ButtonDefaults.outlinedButtonColors(containerColor = palette.lightBtn),
                    border = null,
                    modifier = Modifier.height(48.dp),
                  ) { Text("Previous", color = palette.text) }
                  OutlinedButton(
                    onClick = { vm.selectHit(state.currentHitIndex + 1) },
                    enabled = mr.hits.size >= 2,
                    colors = ButtonDefaults.outlinedButtonColors(containerColor = palette.lightBtn),
                    border = null,
                    modifier = Modifier.height(48.dp),
                  ) { Text("Next", color = palette.text) }
                  OutlinedButton(
                    onClick = { vm.clearHighlight() },
                    colors = ButtonDefaults.outlinedButtonColors(containerColor = palette.lightBtn),
                    border = null,
                    modifier = Modifier.height(48.dp),
                  ) { Text("Clear highlight", color = palette.text) }
                  Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Match inside words", fontSize = 13.sp, color = palette.text)
                    Spacer(Modifier.width(6.dp))
                    Switch(
                      checked = state.matchInsideWords,
                      onCheckedChange = { vm.toggleInsideWords(it) },
                    )
                  }
                }
              }

              if (mr.hits.isNotEmpty()) {
                LazyColumn(modifier = Modifier.fillMaxWidth().heightIn(max = 150.dp)) {
                  itemsIndexed(mr.hits) { idx, hit ->
                    HitRowItem(hit = hit, isSelected = idx == state.currentHitIndex) {
                      vm.selectHit(idx)
                    }
                  }
                }
                HorizontalDivider(color = palette.divider)
              }
            }

            // Lazy Page Viewer
            Box(
              modifier = Modifier
                .fillMaxWidth()
                .height(440.dp)
                .background(palette.viewerBg),
            ) {
              if (activeDoc == null) {
                Box(modifier = Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.Center) {
                  Text(
                    "No files yet. Tap Add files and choose a .txt, .md, or .csv file. Its text appears here page by page, and its words become suggestions.",
                    color = palette.muted,
                    fontSize = 15.sp,
                    textAlign = TextAlign.Center,
                  )
                }
              } else {
                val curHit = mr?.hits?.getOrNull(state.currentHitIndex)?.takeIf { it.doc == activeDoc.name }
                LazyColumn(
                  state = viewerListState,
                  contentPadding = PaddingValues(14.dp),
                  verticalArrangement = Arrangement.spacedBy(14.dp),
                  modifier = Modifier.fillMaxSize(),
                ) {
                  itemsIndexed(activeDoc.pages) { _, page ->
                    PageCardView(
                      docName = activeDoc.name,
                      page = page,
                      totalPages = activeDoc.pages.size,
                      lineSpans = mr?.lineSpans ?: emptyMap(),
                      currentK = curHit?.k ?: -1,
                    )
                  }
                }
              }
            }

            // Footer: Page [n] of N [Go]
            HorizontalDivider(color = palette.divider)
            Row(
              modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
              verticalAlignment = Alignment.CenterVertically,
              horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
              Text("Page", fontSize = 14.sp, color = palette.muted)
              OutlinedTextField(
                value = pageInputText,
                onValueChange = { pageInputText = it.filter { ch -> ch.isDigit() } },
                singleLine = true,
                textStyle = TextStyle(fontSize = 16.sp, color = palette.text),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier.width(72.dp),
              )
              Text("of ${activeDoc?.pages?.size ?: 0}", fontSize = 14.sp, color = palette.muted)
              OutlinedButton(
                onClick = {
                  val total = activeDoc?.pages?.size ?: 0
                  if (total > 0) {
                    val p = (pageInputText.toIntOrNull() ?: 1).coerceIn(1, total)
                    pageInputText = p.toString()
                    scope.launch { viewerListState.animateScrollToItem(p - 1) }
                  }
                },
                shape = RoundedCornerShape(8.dp),
                colors = ButtonDefaults.outlinedButtonColors(containerColor = palette.lightBtn),
                border = null,
                modifier = Modifier.height(48.dp),
              ) { Text("Go", color = palette.text) }
            }
          }
        }

        // Bottom section
        Spacer(Modifier.height(28.dp))
        HorizontalDivider(color = palette.border)
        Spacer(Modifier.height(18.dp))

        Text("Your files and words", fontSize = 16.sp, fontWeight = FontWeight.Bold, color = palette.text)
        Spacer(Modifier.height(10.dp))
        OutlinedButton(
          onClick = { showResetConfirm = true },
          shape = RoundedCornerShape(10.dp),
          colors = ButtonDefaults.outlinedButtonColors(containerColor = palette.lightBtn),
          border = null,
          modifier = Modifier.height(48.dp).testTag("reset_button"),
        ) { Text("Reset learned data", fontSize = 14.sp, color = palette.text) }

        Spacer(Modifier.height(10.dp))
        Text(
          "Add .txt, .md or .csv files with the button above. Each file is shown page by page, and its words become suggestions. A word-list file can give a starting rank after a comma, e.g. python tutorial,5. Lines starting with # are shown but not learned.",
          fontSize = 13.sp,
          color = palette.muted,
        )
        Spacer(Modifier.height(8.dp))
        Text(
          "${FulgurConstants.SAMPLE_WORDS.size} sample words + ${state.docs.size} file(s) you added. ${state.infoNote}".trim(),
          fontSize = 14.sp,
          color = palette.text,
        )

        Spacer(Modifier.height(18.dp))
        Text("Your most searched", fontSize = 16.sp, fontWeight = FontWeight.Bold, color = palette.text)
        Spacer(Modifier.height(6.dp))
        val top5 = remember(state.searches) {
          state.searches.sortedWith(
            compareByDescending<com.example.engine.SearchRecord> { it.count }
              .thenByDescending { it.lastSearchedAtMs }
              .thenBy { it.word }
          ).take(5)
        }
        if (top5.isEmpty()) {
          Text("Nothing yet. Search a word and tap Search.", fontSize = 14.sp, color = palette.muted)
        } else {
          top5.forEachIndexed { idx, rec ->
            Row(
              verticalAlignment = Alignment.CenterVertically,
              modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
            ) {
              Text(
                "${idx + 1}. ${rec.word} (${rec.count}x)",
                fontSize = 15.sp,
                color = palette.topListText,
                modifier = Modifier.weight(1f),
              )
              IconButton(
                onClick = { vm.deleteSearch(rec.word) },
                modifier = Modifier.minimumInteractiveComponentSize(),
              ) {
                Icon(Icons.Default.Close, contentDescription = "Delete ${rec.word}", tint = palette.muted)
              }
            }
          }
        }
      }
    }
  }

  // Dialogs
  docToRemove?.let { name ->
    AlertDialog(
      onDismissRequest = { docToRemove = null },
      title = { Text("Remove file?") },
      text = { Text("Remove $name from Fulgur Search?") },
      confirmButton = {
        Button(onClick = {
          vm.removeDoc(name)
          docToRemove = null
        }) { Text("Remove") }
      },
      dismissButton = {
        TextButton(onClick = { docToRemove = null }) { Text("Cancel") }
      },
    )
  }

  if (showResetConfirm) {
    AlertDialog(
      onDismissRequest = { showResetConfirm = false },
      title = { Text("Reset learned data?") },
      text = { Text("Forget your searches and loaded files? You will have 8 seconds to undo.") },
      confirmButton = {
        Button(onClick = {
          showResetConfirm = false
          vm.startUndoableReset()
        }) { Text("Reset") }
      },
      dismissButton = {
        TextButton(onClick = { showResetConfirm = false }) { Text("Cancel") }
      },
    )
  }

  state.duplicatePrompt?.let { dup ->
    AlertDialog(
      onDismissRequest = { vm.resolveDuplicate(replace = false, cancel = true) },
      title = { Text("File already exists") },
      text = { Text("\"${dup.originalName}\" already exists. Replace it, or keep both as \"${dup.suggestedAltName}\"?") },
      confirmButton = {
        Button(onClick = { vm.resolveDuplicate(replace = true, cancel = false) }) { Text("Replace") }
      },
      dismissButton = {
        Row {
          TextButton(onClick = { vm.resolveDuplicate(replace = false, cancel = true) }) { Text("Cancel") }
          TextButton(onClick = { vm.resolveDuplicate(replace = false, cancel = false) }) { Text("Keep both") }
        }
      },
    )
  }
}

@Composable
private fun HitRowItem(hit: MatchHit, isSelected: Boolean, onClick: () -> Unit) {
  val palette = LocalFulgurPalette.current
  val from = (hit.idx - 40).coerceAtLeast(0)
  val to = (hit.idx + hit.len + 60).coerceAtMost(hit.text.length)
  val safeIdx = hit.idx.coerceIn(from, to)
  val safeEnd = (hit.idx + hit.len).coerceIn(safeIdx, to)
  Column(
    modifier = Modifier
      .fillMaxWidth()
      .background(if (isSelected) palette.hitSelected else palette.card)
      .clickable(onClick = onClick)
      .padding(horizontal = 14.dp, vertical = 8.dp),
  ) {
    Text("${hit.doc}, page ${hit.page}, line ${hit.line}", fontSize = 12.sp, color = palette.muted)
    Text(
      text = buildAnnotatedString {
        if (from > 0) append("…")
        append(hit.text.substring(from, safeIdx))
        withStyle(SpanStyle(background = palette.highlightBg, color = palette.highlightText, fontWeight = FontWeight.SemiBold)) {
          append(hit.text.substring(safeIdx, safeEnd))
        }
        append(hit.text.substring(safeEnd, to))
        if (to < hit.text.length) append("…")
      },
      fontSize = 14.sp,
      color = palette.text,
      maxLines = 2,
      overflow = TextOverflow.Ellipsis,
    )
  }
  HorizontalDivider(color = palette.divider)
}

@Composable
private fun PageCardView(
  docName: String,
  page: DocPage,
  totalPages: Int,
  lineSpans: Map<Triple<String, Int, Int>, List<LineSpan>>,
  currentK: Int,
) {
  val palette = LocalFulgurPalette.current
  Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
    Card(
      colors = CardDefaults.cardColors(containerColor = palette.card),
      shape = RoundedCornerShape(4.dp),
      elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
      modifier = Modifier.widthIn(max = 580.dp).fillMaxWidth(),
    ) {
      Column(modifier = Modifier.padding(horizontal = 18.dp, vertical = 14.dp)) {
        Row(
          modifier = Modifier.fillMaxWidth().padding(bottom = 6.dp),
          horizontalArrangement = Arrangement.SpaceBetween,
        ) {
          Text("Page ${page.number} of $totalPages", fontSize = 12.sp, color = palette.muted)
          Text(docName, fontSize = 12.sp, color = palette.muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        HorizontalDivider(color = palette.divider, modifier = Modifier.padding(bottom = 10.dp))

        SelectionContainer {
          Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            page.lines.forEach { line ->
              val spans = lineSpans[Triple(docName, page.number, line.number)].orEmpty()
              Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
              ) {
                DisableSelection {
                  Text(
                    text = line.number.toString(),
                    fontSize = 12.sp,
                    color = palette.lineNo,
                    textAlign = TextAlign.End,
                    modifier = Modifier.width(34.dp).padding(top = 2.dp),
                  )
                }
                val annotated = buildAnnotatedString {
                  if (spans.isEmpty()) {
                    append(line.text.ifEmpty { " " })
                  } else {
                    var cursor = 0
                    for (sp in spans.sortedWith(compareBy({ it.start }, { it.end }))) {
                      val start = maxOf(cursor, sp.start).coerceAtMost(line.text.length)
                      val end = maxOf(start, sp.end).coerceAtMost(line.text.length)
                      if (start > cursor) append(line.text.substring(cursor, start))
                      if (end > start) {
                        val isCur = sp.k == currentK
                        withStyle(
                          SpanStyle(
                            background = if (isCur) palette.currentMatchBg else palette.highlightBg,
                            color = palette.highlightText,
                            fontWeight = if (isCur) FontWeight.Bold else FontWeight.Normal,
                          ),
                        ) {
                          append(line.text.substring(start, end))
                        }
                        cursor = end
                      }
                    }
                    if (cursor < line.text.length) append(line.text.substring(cursor))
                  }
                }
                Text(
                  text = annotated,
                  fontSize = 15.sp,
                  lineHeight = 23.sp,
                  color = palette.text,
                  modifier = Modifier.weight(1f),
                )
              }
            }
          }
        }
      }
    }
  }
}
