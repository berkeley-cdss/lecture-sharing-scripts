# Scripts for working with the bCourses Media Gallery & Kaltura

These scripts were designed for [CS70](https://www.eecs70.org/). We're sharing them so others can adapt them to their courses! 

For context, CS70 uses UC Berkeley's [Course Capture](https://rtl.berkeley.edu/services-programs/course-capture) service to record its lectures. These recordings are automatically added to the ["Media Gallery" tab](https://knowledge.kaltura.com/help/access-and-work-in-the-media-gallery) on bCourses (Canvas). We maintain our own website (see [eecs70.org](https://www.eecs70.org/)) and have links bCourses for lecture recordings.

The process for linking a lecture recording on the website is:

* Create a bCourses page for the lecture.
* Embed the video from the media gallery onto that bCourses page using the Canvas editor.
* Link the bCourses page on the website for students to access.

This is a slightly monotonous task that Head TAs have to do for every lecture. Manually doing this also causes a delay between the recording being available and the recording being listed on the website. This inconveniences students.

We built these scripts to automate the process.

**The first script is `scrape_webcasts.py`.** It is the script that will (via bCourses), generate a list of every video in your media gallery and a link to it. You can see an example of its output in `examples/media-gallery.csv`.

The inputs you can provide the script are: `--course-id`, `--tool-id`, `--channel-path`, and `--output`. `--output` is just the filename for the CSV you'd like to save. `--course-id` and `--tool-id` can be extracted from the URL of your media gallery, eg. CS 70's is `https://bcourses.berkeley.edu/courses/1551726/external_tools/90481`. And then to find the `--channel-path`, you can inspect the media gallery in bCourses and get the embedded URL: 

<img width="400" alt="HTML of the media gallery in bCourses" src="https://github.com/user-attachments/assets/177f65af-ea1d-4575-b05b-6f7068e6bd70" />


Here's an example of running the script:

```
CANVAS_API_TOKEN="your_token" python3 _utils/scrape_webcasts.py --course-id 1551726 --tool-id 90481 --channel-path /channel/1551726/397920713 --output _data/webcasts.csv
```

**The second script is `sync_webcast_pages.py`.** It is a little bit more specific to CS 70 but it should be adaptable to your course. It takes the output of the scraper and creates individual bCourses pages for each lecture. It then outputs a CSV of the bCourses pages for each lecture. We then use that CSV to display them on the course website. The inputs are `--course-id` (on Canvas), `--webcasts-csv` (the CSV that the previous script generated), `--weeks-yml` (CS70-specific, this is our course schedule that the website is built off of), and `--output` (path of the CSV you'd like it to output). The important chunk of code is this chunk here (and the functions it calls):

```python
lookup_uuid = create_resource_link(
  session, args.course_id, lec["entry_id"], lec["title"]
)

body = build_embed_body(args.course_id, lookup_uuid, lec["title"])

page = create_page(session, args.course_id, lec["page_title"], body)
page_slug = page["url"]
print(f"  {lec['page_title']}: created -> {page_slug}")

created.append(lec)
```

Figuring out that you needed to use [this API](https://developerdocs.instructure.com/services/canvas/resources/lti_resource_links) to find the `lookup_uuid` was the hardest part of this. Happy to help anyone adapt the script to their courses! I've also attached an example of the output in `examples/webcast_pages.csv`.
