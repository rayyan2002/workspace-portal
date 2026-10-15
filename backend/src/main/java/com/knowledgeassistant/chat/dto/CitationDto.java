package com.knowledgeassistant.chat.dto;

import com.knowledgeassistant.citation.Citation;

import java.util.UUID;

/**
 * Shape fixed by the frontend contract the citation cards were built against —
 * documentName is denormalised in so the card can render without a second request.
 */
public record CitationDto(
        UUID id,
        UUID documentId,
        String documentName,
        String section,
        Integer page,
        String matchQuality,
        String excerpt
) {
    /**
     * A WORD, not a percentage, and the wording is the point.
     *
     * <p>The number behind it is cosine similarity between the question and the passage —
     * how well retrieval matched, which is not how likely the answer is to be right.
     * Rendering "92%" next to a 0.5B model's output would be a confident signal about
     * something nobody measured, which is the exact failure this project keeps catching.
     *
     * <p>The band comes from the Day 6 measurements rather than intuition: questions the
     * corpus provably cannot answer top out at <strong>0.518</strong>, min_score is
     * <strong>0.60</strong>, and the two genuine answerable anchors scored <strong>0.695</strong>
     * and <strong>0.752</strong>.
     *
     * <p>It was 0.70 for about ten minutes, which was wrong and the first real citation said
     * so: a live answer scored <strong>0.696</strong> and came back "Partial match" — a
     * genuine, correct, on-topic citation put in the lower band because the line sat one
     * thousandth above a measured good match. Set to 0.68, just below the lowest genuine
     * anchor.
     *
     * <p><strong>Day 13 tried to place this properly and could not. The honest result is
     * recorded rather than replaced with a better-looking number.</strong> The golden set
     * produced three resolved citations on the local backend:
     *
     * <pre>
     *   0.634  Partial match   correct document
     *   0.681  Close match     correct document
     *   0.732  Close match     correct document
     * </pre>
     *
     * <p>All three pointed at the RIGHT document, and they straddle 0.68. So on the evidence
     * available the band does not predict whether a citation is correct — it reports
     * retrieval similarity, which is exactly what it claims and what the tooltip says, and
     * nothing more. A user reading "Partial match" beside a perfectly correct citation is
     * being told something true and unhelpful.
     *
     * <p>Three points is too few to move the line and too few to remove the label, so both
     * stay. What changed is that the limitation is now measured instead of assumed. More data
     * needs more resolved citations, and the local model only resolves about 43% of them —
     * which makes this a generation problem wearing a threshold's clothes.
     */
    static String qualityFor(Float score) {
        if (score == null) {
            return "Unknown match";
        }
        return score >= 0.68f ? "Close match" : "Partial match";
    }

    public static CitationDto from(Citation citation) {
        return new CitationDto(
                citation.getId(),
                citation.getDocument().getId(),
                citation.getDocument().getFilename(),
                citation.getSection(),
                citation.getPage(),
                qualityFor(citation.getScore()),
                citation.getExcerpt());
    }
}
