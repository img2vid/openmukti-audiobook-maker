# How to Name Books, Chapters, and Cover Images

Create one folder for every book. Put chapter text files and matching images in that book folder.

Best matching pattern:

```
My Library/
  Fiction Book/
    Chapter 01.txt
    Chapter 01.png
    Chapter 02.txt
    Chapter 02.jpg
    Chapter 03.txt
    Chapter 03.png
  Nonfiction Book/
    Chapter 01.txt
    Chapter 01.webp
    Chapter 02.txt
    Chapter 02.png
```

Exact base-name matches take precedence. The program also tries the unique chapter number. A cover named `cover.jpg` can act as a fallback for every chapter; use that only if you want the same cover for the whole book. If two images share the same chapter number, correct the match inside the app. Use **Combine Chapters** → **Assign selected chapter cover**.

Recorded audio can use the same names, e.g. `Chapter 01.mp3` and `Chapter 01.jpg`. You may also provide a `books.json` manifest to match arbitrarily named art, text, and narration. For whole ebooks, click **Add many ebooks**; when chapter identification is ambiguous, verify the preview and use a manifest for precise mapping.
