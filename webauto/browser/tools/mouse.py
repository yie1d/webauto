from typing import Literal

from cdpkit.connection import CDPSessionExecutor
from cdpkit.protocol import Input


class Mouse(CDPSessionExecutor):

    def press(
        self,
        x: float,
        y: float,
        modifiers: int | None = None,
        timestamp: Input.TimeSinceEpoch | None = None,
        button: Input.MouseButton | None = None,
        buttons: int | None = None,
        click_count: int | None = None,
        force: float | None = None,
        tangential_pressure: float | None = None,
        tilt_x: float | None = None,
        tilt_y: float | None = None,
        twist: int | None = None,
        delta_x: float | None = None,
        delta_y: float | None = None,
        pointer_type: Literal['mouse', 'pen'] | None = None
    ):
        self.execute_method(
            Input.DispatchMouseEvent(
                type_='mousePressed',
                x=x,
                y=y,
                modifiers=modifiers,
                timestamp=timestamp,
                button=button,
                buttons=buttons,
                click_count=click_count,
                force=force,
                tangential_pressure=tangential_pressure,
                tilt_x=tilt_x,
                tilt_y=tilt_y,
                twist=twist,
                delta_x=delta_x,
                delta_y=delta_y,
                pointer_type=pointer_type
            )
        )

    def move(
        self,
        x: float,
        y: float,
        modifiers: int | None = None,
        timestamp: Input.TimeSinceEpoch | None = None,
        button: Input.MouseButton | None = None,
        buttons: int | None = None,
        click_count: int | None = None,
        force: float | None = None,
        tangential_pressure: float | None = None,
        tilt_x: float | None = None,
        tilt_y: float | None = None,
        twist: int | None = None,
        delta_x: float | None = None,
        delta_y: float | None = None,
        pointer_type: Literal['mouse', 'pen'] | None = None
    ):
        self.execute_method(
            Input.DispatchMouseEvent(
                type_='mouseMoved',
                x=x,
                y=y,
                modifiers=modifiers,
                timestamp=timestamp,
                button=button,
                buttons=buttons,
                click_count=click_count,
                force=force,
                tangential_pressure=tangential_pressure,
                tilt_x=tilt_x,
                tilt_y=tilt_y,
                twist=twist,
                delta_x=delta_x,
                delta_y=delta_y,
                pointer_type=pointer_type
            )
        )

    def release(
        self,
        x: float,
        y: float,
        modifiers: int | None = None,
        timestamp: Input.TimeSinceEpoch | None = None,
        button: Input.MouseButton | None = None,
        buttons: int | None = None,
        click_count: int | None = None,
        force: float | None = None,
        tangential_pressure: float | None = None,
        tilt_x: float | None = None,
        tilt_y: float | None = None,
        twist: int | None = None,
        delta_x: float | None = None,
        delta_y: float | None = None,
        pointer_type: Literal['mouse', 'pen'] | None = None
    ):
        self.execute_method(
            Input.DispatchMouseEvent(
                type_='mouseReleased',
                x=x,
                y=y,
                modifiers=modifiers,
                timestamp=timestamp,
                button=button,
                buttons=buttons,
                click_count=click_count,
                force=force,
                tangential_pressure=tangential_pressure,
                tilt_x=tilt_x,
                tilt_y=tilt_y,
                twist=twist,
                delta_x=delta_x,
                delta_y=delta_y,
                pointer_type=pointer_type
            )
        )
