import sqlite3


TASK_ID = "537aebdc4bd345999cb11348934dc538"
CITES_URL = "https://scholar.lanfanshu.cn/scholar?cites=1204426401771612558"
PDF_URL = "http://openaccess.thecvf.com/content/ICCV2023/papers/Wang_CORE_Cooperative_Reconstruction_for_Multi-Agent_Perception_ICCV_2023_paper.pdf"


def main() -> None:
    con = sqlite3.connect("dev.sqlite3")
    con.execute("DELETE FROM scholar_results WHERE task_id=? AND role='citation_b'", (TASK_ID,))
    con.execute(
        """
        UPDATE scholar_results
        SET cited_by_url=?, pdf_url=?
        WHERE task_id=? AND role='candidate_a' AND title LIKE 'Core:%'
        """,
        (CITES_URL, PDF_URL, TASK_ID),
    )
    con.execute(
        """
        UPDATE tasks
        SET cited_by_url=?, status='paper_confirmed', current_page=0,
            message='已修复 cited-by URL，请重新采集 B'
        WHERE id=?
        """,
        (CITES_URL, TASK_ID),
    )
    con.commit()
    print("fixed")


if __name__ == "__main__":
    main()
