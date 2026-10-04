from typing import Annotated

from fastapi import Header, HTTPException


async def get_student_id(
    x_student_id: Annotated[
        str | None,
        Header(alias="X-Student-ID")
    ] = None,
) -> str:

    if not x_student_id:

        raise HTTPException(
            status_code=401,
            detail="Missing student identity.",
        )

    if len(x_student_id) > 128:

        raise HTTPException(
            status_code=400,
            detail="Invalid student identity.",
        )

    return x_student_id
