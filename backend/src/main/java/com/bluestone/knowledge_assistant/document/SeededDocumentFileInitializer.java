package com.bluestone.knowledge_assistant.document;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

/**
 * Materialises placeholder files for seeded documents that have metadata but no bytes.
 *
 * <p>The four documents seeded in V8 were rows only — nothing was ever written to disk
 * for them. Without this, "open the original" would 404 on every document in a fresh
 * checkout until the user uploaded something, and user B's library would be entirely
 * unopenable. Writing a small stand-in makes the feature demonstrable immediately.
 *
 * <p>Dev and test only: in a real environment a document row with no file is a genuine
 * data problem and must surface as one, not be papered over with invented content.
 */
@Component
@Profile({"dev", "test", "local", "default"})
public class SeededDocumentFileInitializer implements ApplicationListener<ApplicationReadyEvent> {

    private static final Logger log = LoggerFactory.getLogger(SeededDocumentFileInitializer.class);

    private final DocumentRepository documentRepository;
    private final String uploadDir;

    public SeededDocumentFileInitializer(DocumentRepository documentRepository,
                                         @Value("${app.uploads.dir:uploads}") String uploadDir) {
        this.documentRepository = documentRepository;
        this.uploadDir = uploadDir;
    }

    @Override
    @Transactional(readOnly = true)
    public void onApplicationEvent(ApplicationReadyEvent event) {
        try {
            Path root = Paths.get(uploadDir).toAbsolutePath().normalize();
            Files.createDirectories(root);

            int created = 0;
            for (Document document : documentRepository.findAll()) {
                if (document.getStoragePath() == null) continue;

                Path target = root.resolve(document.getId().toString());
                if (Files.exists(target)) continue;

                Files.write(target, placeholderFor(document));
                created++;
            }

            if (created > 0) {
                log.info("Created {} placeholder file(s) for seeded documents in {}", created, root);
            }
        } catch (IOException e) {
            // A demo convenience must never stop the application from starting.
            log.warn("Could not materialise placeholder document files: {}", e.getMessage());
        }
    }

    private byte[] placeholderFor(Document document) {
        String filename = document.getFilename();

        if (filename.toLowerCase().endsWith(".pdf")) {
            return minimalPdf(filename, "Placeholder content for a seeded demo document.");
        }

        String text = """
                # %s

                Placeholder content for a seeded demo document.

                This file exists so that "open the original" is demonstrable without
                uploading something first. Real uploads store the bytes you actually sent.

                Document id: %s
                """.formatted(filename, document.getId());

        return text.getBytes(StandardCharsets.UTF_8);
    }

    /**
     * Builds a genuinely valid single-page PDF, xref table and all.
     *
     * <p>Writing text into a .pdf would produce a file the browser refuses to render,
     * which would look exactly like the download being broken. Byte offsets are taken
     * from the buffer length, which is only correct because every byte written here is
     * ASCII.
     */
    private byte[] minimalPdf(String title, String body) {
        List<String> objects = new ArrayList<>();
        objects.add("<< /Type /Catalog /Pages 2 0 R >>");
        objects.add("<< /Type /Pages /Kids [3 0 R] /Count 1 >>");
        objects.add("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                + "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>");
        objects.add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");

        String stream = "BT /F1 16 Tf 72 720 Td (" + escapePdf(title) + ") Tj ET\n"
                + "BT /F1 11 Tf 72 690 Td (" + escapePdf(body) + ") Tj ET";
        objects.add("<< /Length " + stream.length() + " >>\nstream\n" + stream + "\nendstream");

        StringBuilder pdf = new StringBuilder("%PDF-1.4\n");
        int[] offsets = new int[objects.size() + 1];

        for (int i = 0; i < objects.size(); i++) {
            offsets[i + 1] = pdf.length();
            pdf.append(i + 1).append(" 0 obj\n").append(objects.get(i)).append("\nendobj\n");
        }

        int xrefOffset = pdf.length();
        pdf.append("xref\n0 ").append(objects.size() + 1).append('\n');
        pdf.append("0000000000 65535 f \n");
        for (int i = 1; i <= objects.size(); i++) {
            pdf.append(String.format("%010d 00000 n %n", offsets[i]).replace(System.lineSeparator(), "\n"));
        }
        pdf.append("trailer\n<< /Size ").append(objects.size() + 1).append(" /Root 1 0 R >>\n");
        pdf.append("startxref\n").append(xrefOffset).append("\n%%EOF");

        return pdf.toString().getBytes(StandardCharsets.US_ASCII);
    }

    /** Parentheses and backslashes delimit PDF string literals, so they must be escaped. */
    private String escapePdf(String value) {
        return value.replaceAll("[^\\x20-\\x7E]", "")
                .replace("\\", "\\\\")
                .replace("(", "\\(")
                .replace(")", "\\)");
    }
}
