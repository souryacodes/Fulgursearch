package com.example.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

@Immutable
data class FulgurPalette(
  val bg: Color,
  val card: Color,
  val text: Color,
  val primary: Color,
  val onPrimary: Color,
  val muted: Color,
  val border: Color,
  val lightBtn: Color,
  val suggestionActive: Color,
  val divider: Color,
  val lineNo: Color,
  val hitBarBg: Color,
  val hitBarBorder: Color,
  val hitSelected: Color,
  val highlightBg: Color,
  val highlightText: Color,
  val currentMatchBg: Color,
  val currentMatchOutline: Color,
  val topListText: Color,
  val viewerBg: Color,
)

private val LightPalette = FulgurPalette(
  bg = FulgurBgLight,
  card = FulgurCardLight,
  text = FulgurTextLight,
  primary = FulgurPrimaryLight,
  onPrimary = Color.White,
  muted = FulgurMutedLight,
  border = FulgurBorderLight,
  lightBtn = FulgurLightBtnLight,
  suggestionActive = FulgurSuggestionActiveLight,
  divider = FulgurDividerLight,
  lineNo = FulgurLineNoLight,
  hitBarBg = FulgurHitBarLight,
  hitBarBorder = FulgurHitBarBorderLight,
  hitSelected = FulgurHitSelectedLight,
  highlightBg = FulgurHighlightLight,
  highlightText = FulgurTextLight,
  currentMatchBg = FulgurCurrentMatchLight,
  currentMatchOutline = FulgurCurrentOutlineLight,
  topListText = FulgurTopListLight,
  viewerBg = FulgurViewerBgLight,
)

private val DarkPalette = FulgurPalette(
  bg = FulgurBgDark,
  card = FulgurCardDark,
  text = FulgurTextDark,
  primary = FulgurPrimaryDark,
  onPrimary = Color(0xFF0B1120),
  muted = FulgurMutedDark,
  border = FulgurBorderDark,
  lightBtn = FulgurLightBtnDark,
  suggestionActive = FulgurSuggestionActiveDark,
  divider = FulgurDividerDark,
  lineNo = Color(0xFF6E7A96),
  hitBarBg = FulgurHitBarDark,
  hitBarBorder = FulgurHitBarBorderDark,
  hitSelected = FulgurHitSelectedDark,
  highlightBg = FulgurHighlightLight,
  highlightText = FulgurTextLight,
  currentMatchBg = FulgurCurrentMatchLight,
  currentMatchOutline = FulgurCurrentOutlineLight,
  topListText = Color(0xFFCBD5E1),
  viewerBg = FulgurViewerBgDark,
)

val LocalFulgurPalette = staticCompositionLocalOf { LightPalette }

private val LightColorScheme = lightColorScheme(
  primary = FulgurPrimaryLight,
  onPrimary = Color.White,
  background = FulgurBgLight,
  onBackground = FulgurTextLight,
  surface = FulgurCardLight,
  onSurface = FulgurTextLight,
  surfaceVariant = FulgurLightBtnLight,
  onSurfaceVariant = FulgurMutedLight,
  outline = FulgurBorderLight,
)

private val DarkColorScheme = darkColorScheme(
  primary = FulgurPrimaryDark,
  onPrimary = Color(0xFF0B1120),
  background = FulgurBgDark,
  onBackground = FulgurTextDark,
  surface = FulgurCardDark,
  onSurface = FulgurTextDark,
  surfaceVariant = FulgurLightBtnDark,
  onSurfaceVariant = FulgurMutedDark,
  outline = FulgurBorderDark,
)

@Composable
fun MyApplicationTheme(
  darkTheme: Boolean = isSystemInDarkTheme(),
  content: @Composable () -> Unit,
) {
  val palette = if (darkTheme) DarkPalette else LightPalette
  val colorScheme = if (darkTheme) DarkColorScheme else LightColorScheme
  CompositionLocalProvider(LocalFulgurPalette provides palette) {
    MaterialTheme(
      colorScheme = colorScheme,
      typography = Typography,
      content = content,
    )
  }
}
