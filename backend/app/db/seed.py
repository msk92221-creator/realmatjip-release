"""fixture 시드 — Phase 1은 mock analyzer + synthetic 데이터로 전체 흐름을 증명한다.

실행: python -m app.db.seed [--reset] [--db PATH]
"""
import argparse

from fixtures.dataset import build_dataset

from .database import init_db, make_engine, make_session_factory
from .mappers import analysis_to_row, restaurant_to_row, review_to_row
from .models import Base, JobORM, RestaurantScoreORM, ReviewAnalysisORM, ReviewORM, RestaurantORM


def seed(session, reset: bool = False) -> dict:
    if reset:
        for table in (RestaurantScoreORM, ReviewAnalysisORM, ReviewORM, RestaurantORM, JobORM):
            session.query(table).delete()
    restaurants, reviews = build_dataset()
    for rest in restaurants:
        session.merge(restaurant_to_row(rest))
    for review in reviews:
        session.merge(review_to_row(review))
        session.merge(analysis_to_row(review.id, review.analysis))
    session.commit()
    return {"restaurants": len(restaurants), "reviews": len(reviews)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed fixture dataset into SQLite")
    parser.add_argument("--db", default="realmatjip.db")
    parser.add_argument("--reset", action="store_true", help="기존 데이터 삭제 후 시드")
    args = parser.parse_args()

    engine = make_engine("sqlite:///" + args.db)
    Base.metadata.create_all(engine)
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        result = seed(session, reset=args.reset)
    print(f"시드 완료: {result} → {args.db}")


if __name__ == "__main__":
    main()
