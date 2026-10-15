package com.bluestone.knowledge_assistant.chat.dto;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * The confidence label, and where its line sits.
 *
 * <p>A word rather than a percentage, deliberately: the number behind it is cosine
 * similarity between the question and the passage — how well RETRIEVAL matched, which is not
 * how likely the answer is to be right. "92%" beside a 0.5B model's output would be a
 * confident claim about something nobody measured.
 */
class CitationDtoTest {

    @Test
    void theBandSitsBelowTheLowestGenuineAnchor() {
        // 0.695 and 0.752 are the two genuine answerable anchors from the Day 6 calibration.
        // The first real citation of Day 9 scored 0.696, and a 0.70 line called it "Partial"
        // — a correct, on-topic citation demoted because the threshold sat one thousandth
        // above a measured good match.
        assertEquals("Close match", CitationDto.qualityFor(0.696f));
        assertEquals("Close match", CitationDto.qualityFor(0.695f));
        assertEquals("Close match", CitationDto.qualityFor(0.752f));
    }

    @Test
    void scoresJustOverTheRetrievalFloorArePartial() {
        // min_score is 0.60. Anything scraping in just above it matched, but not closely.
        assertEquals("Partial match", CitationDto.qualityFor(0.61f));
        assertEquals("Partial match", CitationDto.qualityFor(0.67f));
    }

    @Test
    void aMissingScoreSaysSoRatherThanGuessing() {
        // Citations written before V19 have no score. Reporting them as a good match would
        // invent a measurement; reporting them as poor would libel them.
        assertEquals("Unknown match", CitationDto.qualityFor(null));
    }
}
