"""Interactive in/out-flux plot embedded inline in the CNApy console.

This module owns everything needed to:

- compute the in/out flux bar plot for a single metabolite
  (:meth:`InOutFluxConsolePlot.in_out_fluxes`, called e.g. from
  ``cna.print_in_out_fluxes(...)`` in the console),
- render it as a fixed-width image inserted into the QtConsole's
  scrollback next to a clickable legend (reaction and metabolite IDs are
  clickable links, using the same ``cnapy-reaction:``/``cnapy-metabolite:``
  href scheme as e.g. ``reactions_list.build_reaction_equation_html``), and
- make the individual stacked-bar segments in the resulting inline image
  clickable too, via a Qt event filter installed on the console's
  viewport.

A single :class:`InOutFluxConsolePlot` instance is created by
:class:`~cnapy.gui_elements.main_window.MainWindow` and lives for as long
as the console does, so old plots further up in the scrollback stay fully
interactive.
"""
from io import BytesIO
from urllib.parse import quote, unquote

import matplotlib.pyplot as plt
from matplotlib.colors import to_hex

from qtpy.QtCore import QEvent, QObject, QRect, QUrl, Qt, Signal
from qtpy.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QPalette,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextImageFormat,
    QTextLength,
    QTextTableFormat,
)
from qtpy.QtWidgets import QToolTip


class InOutFluxConsolePlot(QObject):
    """Computes and displays a clickable in/out-flux plot in the console."""

    # Emitted when an inline-console link created by this class is clicked
    # (a "Metabolite: X" header link, a legend reaction/metabolite link, or
    # a bar segment in the plot itself). Handled here via an event filter
    # rather than qtconsole's own link handling, so old console output
    # remains fully scrollable and interactive.
    reactionClicked = Signal(str)
    metaboliteClicked = Signal(str)

    def __init__(self, appdata, central_widget):
        super().__init__(central_widget)
        self.appdata = appdata
        self.central_widget = central_widget

        # Inline plots are inserted into the QtConsole document as images.
        # Keep the image-local hit regions so the stacked rectangles can be
        # made interactive even though Matplotlib itself is no longer
        # receiving mouse events after the figure is rendered inline.
        self._console_plot_regions = {}
        self._console_plot_counter = 0
        self._console_plot_tooltip_reaction = None

        # The QtConsole uses a QTextEdit internally for rich output. Install
        # an event filter there so custom cnapy-* hyperlinks and the inline
        # plot hit-testing below work without replacing the inline backend.
        self._console_control = getattr(central_widget.console, "_control", None)
        self._console_viewport = None
        if self._console_control is not None:
            # Qt delivers text-edit mouse events to the viewport. The
            # coordinates passed to QTextEdit.anchorAt() are viewport
            # coordinates, so keep the filter there and do not remap them.
            self._console_viewport = self._console_control.viewport()
            self._console_viewport.installEventFilter(self)
            self.reactionClicked.connect(central_widget.jump_to_reaction)
            self.metaboliteClicked.connect(central_widget.jump_to_metabolite)

    # ------------------------------------------------------------------
    # Computing and inserting a plot
    # ------------------------------------------------------------------
    def in_out_fluxes(self, metabolite_id, soldict):
        self.central_widget.kernel_client.execute('%matplotlib inline', store_history=False)
        # Disable pyplot's interactive mode while building the figure: with
        # an interactive backend active, each individual ax.bar() call below
        # can trigger its own canvas redraw, which visibly adds up for
        # metabolites involved in many reactions. The figure is still
        # rendered explicitly (once) in _append_clickable_flux_plot.
        with plt.ioff(), self.appdata.project.cobra_py_model as model:
            self.appdata.project.scen_values.add_scenario_reactions_to_model(model)
            met = model.metabolites.get_by_id(metabolite_id)
            fig, ax = plt.subplots()
            ax.set_xticks([1, 2])
            ax.set_xticklabels(['In', 'Out'])
            cons = []
            prod = []
            sum_cons = 0
            sum_prod = 0

            # Keep the matplotlib bar colors so the clickable console legend
            # can visually match the corresponding stacked bars.
            legend_entries = []

            for rxn in met.reactions:
                flux = soldict.get(rxn.id, 0.0)
                if abs(flux) > model.tolerance:
                    flux *= rxn.get_coefficient(metabolite_id)
                    if flux < 0:
                        cons.append((rxn, -flux))
                    elif flux > 0:
                        prod.append((rxn, flux))
            cons = sorted(cons, key=lambda x: x[1], reverse=True)
            prod = sorted(prod, key=lambda x: x[1], reverse=True)

            for rxn, flux in prod:
                bar = ax.bar(
                    1, flux, width=0.8, bottom=sum_prod,
                    label=rxn.id + ": " + rxn.build_reaction_string()
                )
                legend_entries.append((rxn.id, rxn, flux, bar.patches[0]))
                sum_prod += flux

            for rxn, flux in cons:
                bar = ax.bar(
                    2, flux, width=0.8, bottom=sum_cons,
                    label=rxn.id + ": " + rxn.build_reaction_string()
                )
                legend_entries.append((rxn.id, rxn, flux, bar.patches[0]))
                sum_cons += flux

            ax.set_ylabel('Flux')
            ax.set_title('In/Out fluxes at metabolite ' + metabolite_id)

            # Insert plot and clickable legend together as one scrollback item.
            self._append_clickable_flux_plot(
                fig, metabolite_id, legend_entries
            )

        self.central_widget.kernel_client.execute('%matplotlib qt', store_history=False)

        return prod, cons

    def _append_clickable_flux_plot(self, fig, metabolite_id, legend_entries):
        """Insert a fixed-width flux plot and clickable legend side-by-side.

        ``legend_entries`` contains ``(reaction_id, reaction, flux, patch)``.
        The plot is rendered at a fixed physical width so its size does not
        depend on the QtConsole width. The legend contains clickable
        reaction and metabolite IDs and the numerical flux value in front of
        each equation.
        """
        control = self._console_control
        if control is None:
            return

        # Render the matplotlib figure without sending it separately through
        # the inline backend; the rendered image is inserted into the same
        # QTextDocument as the clickable legend.
        # Render at a fixed physical width and a fixed, known dpi. The plot
        # only contains two stacked bars, so a relatively compact width is
        # sufficient.
        fixed_plot_width = 3.2
        fig.set_size_inches(fixed_plot_width, max(2.4, fixed_plot_width * fig.get_figheight() / max(fig.get_figwidth(), 0.1)), forward=True)
        fig.set_dpi(100)

        # Draw the figure exactly once. Previously it was rendered twice --
        # once implicitly via get_renderer() below to compute the legend's
        # clickable hit-boxes, and again via savefig() to produce the PNG --
        # which visibly doubles the redraw cost for metabolites with many
        # reactions (many bar segments). Reading the already-rendered RGBA
        # buffer straight into a QImage also skips a full PNG encode/decode
        # round trip that savefig()+loadFromData() would otherwise do.
        try:
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            image_width = int(renderer.width)
            image_height = int(renderer.height)
            buf = renderer.buffer_rgba()
            # .copy() so the QImage owns its pixel data independently of the
            # renderer's buffer, which is freed once the figure is closed
            # further down (Qt may not actually paint the image until well
            # after that).
            image = QImage(
                buf, image_width, image_height, QImage.Format.Format_RGBA8888
            ).copy()
        except AttributeError:
            # Fallback for a canvas that isn't Agg-based (buffer_rgba() is
            # only available on Agg-derived canvases -- which covers every
            # backend used here, so this should be rare in practice).
            png = BytesIO()
            fig.savefig(png, format="png", dpi=100)
            png.seek(0)
            image = QImage()
            if not image.loadFromData(png.read(), "PNG"):
                return
            renderer = fig.canvas.get_renderer()
            image_width = image.width()
            image_height = image.height()

        # Record one image-local rectangle for each stacked bar, from the
        # very renderer used above (no second render pass). Matplotlib's
        # display coordinate system has its origin at the lower left, while a
        # QImage/Qt text document has its origin at the upper left.
        regions = []
        for reaction_id, _rxn, flux, patch in legend_entries:
            bbox = patch.get_window_extent(renderer)
            x0 = max(0.0, bbox.x0)
            x1 = min(float(image_width), bbox.x1)
            y0 = max(0.0, float(image_height) - bbox.y1)
            y1 = min(float(image_height), float(image_height) - bbox.y0)
            regions.append((x0, y0, x1, y1, reaction_id))

        self._console_plot_counter += 1
        image_id = f"cnapy-flux-plot-{self._console_plot_counter}"

        document = control.document()

        # Find the position of the console's current prompt (if any), so the
        # plot/legend can be inserted *before* it instead of always being
        # appended at the absolute end of the document. kernel_client.execute()
        # (used by in_out_fluxes() above) queues code directly with the
        # kernel, bypassing the console's own execute() bookkeeping -- so
        # whatever prompt was already on screen (waiting for the user, with
        # or without partially typed text) is still sitting at the end of
        # the document while this runs, and appending after it would insert
        # the new output below that prompt instead of above it.
        console_widget = self.central_widget.console
        prompt_pos = getattr(console_widget, "_prompt_pos", None)
        insert_before_prompt = (
            prompt_pos is not None and 0 <= prompt_pos <= document.characterCount()
        )

        if insert_before_prompt:
            cursor = QTextCursor(document)
            cursor.setPosition(prompt_pos)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        else:
            cursor = control.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)

        # Batch every insertion below (table, image, and all legend text/
        # links) into a single edit block. Without this, each of the many
        # small insertText()/insertLink() calls in the legend loop can make
        # Qt re-run layout for the surrounding table on its own, which is
        # the main source of the delay for metabolites with many reactions
        # (many legend entries -> many small edits). Wrapped in one block,
        # Qt defers that to a single pass once endEditBlock() is reached.
        cursor.beginEditBlock()
        cursor.insertBlock()
        # Position of the very top of the newly inserted content, used below
        # to scroll it into view once everything has been inserted.
        top_of_new_content = cursor.position()

        # Fix both column widths so the table's total width is independent of
        # the legend text content. A long reaction equation can then never
        # grow the table (and therefore can no longer push the plot column
        # around / shift the whole thing left) -- it can only wrap or, if
        # it's excessive, get truncated within its own fixed-width cell.
        legend_width_px = max(
            300, min(600, control.viewport().width() - image.width() - 40)
        )
        table_format = QTextTableFormat()
        table_format.setCellPadding(0)
        table_format.setCellSpacing(12)
        table_format.setBorder(0)
        table_format.setColumnWidthConstraints([
            QTextLength(QTextLength.Type.FixedLength, image.width()),
            QTextLength(QTextLength.Type.FixedLength, legend_width_px),
        ])
        table = cursor.insertTable(1, 2, table_format)

        # Left cell: plot. The image is deliberately not rescaled based on
        # console width; its pixel dimensions are fixed by the figure size.
        plot_cursor = table.cellAt(0, 0).firstCursorPosition()

        # Register the image as a document resource so we can identify this
        # particular inline plot later during mouse hit-testing.
        control.document().addResource(
            QTextDocument.ResourceType.ImageResource,
            QUrl(image_id),
            image,
        )
        image_format = QTextImageFormat()
        image_format.setName(image_id)
        image_format.setWidth(image.width())
        image_format.setHeight(image.height())
        image_format.setVerticalAlignment(
            QTextCharFormat.VerticalAlignment.AlignTop
        )
        plot_cursor.insertImage(image_format)

        # Store the image dimensions and reaction hit boxes. The actual screen
        # size is obtained from the image format during hit testing, allowing
        # the method to remain correct if Qt scales the image.
        self._console_plot_regions[image_id] = {
            "width": image.width(),
            "height": image.height(),
            "image_width": image.width(),
            "image_height": image.height(),
            "regions": regions,
        }

        # Right cell: clickable legend.
        legend_cursor = table.cellAt(0, 1).firstCursorPosition()

        # Now that the cell has a fixed width (see above), plain line-wrapping
        # is safe: it can only make an entry's block taller, never widen the
        # table. Each block is still allowed to break, matching the default
        # QTextBlockFormat.
        line_format = QTextBlockFormat()
        legend_cursor.setBlockFormat(line_format)

        def insert_link(text, href, bold=False, tooltip=None):
            fmt = QTextCharFormat()
            fmt.setAnchor(True)
            fmt.setAnchorHref(href)
            fmt.setToolTip(tooltip if tooltip is not None else "Click to select " + text)
            fmt.setForeground(control.palette().color(QPalette.ColorRole.Link))
            if bold:
                fmt.setFontWeight(QFont.Weight.Bold)
            legend_cursor.insertText(text, fmt)

        legend_cursor.insertText("Metabolite: ")
        insert_link(
            metabolite_id,
            "cnapy-metabolite:" + quote(metabolite_id, safe=""),
            bold=True,
        )
        legend_cursor.insertBlock(line_format)
        legend_cursor.insertBlock(line_format)

        # Bound each entry's height instead of letting it wrap indefinitely:
        # a reaction with many metabolites could otherwise wrap onto many
        # lines and make the legend (and thus the whole plot/legend block)
        # very tall. Budget roughly this many wrapped lines' worth of pixel
        # width per entry; anything beyond that is replaced by a plain,
        # non-clickable ellipsis whose tooltip shows the full equation.
        max_equation_lines = 2
        cell_inner_width_px = max(100, legend_width_px - 20)
        fm = QFontMetrics(control.font())

        def insert_reaction_equation(rxn, budget_px):
            """Insert ``rxn``'s equation with each metabolite id as a
            clickable ``cnapy-metabolite:`` link, mirroring the metabolite
            links in reactions_list.build_reaction_equation_html. Stops and
            appends a tooltip-bearing "…" once the estimated rendered width
            exceeds ``budget_px``, so one equation can't blow up the legend's
            height.
            """
            def side_segments(metabolites, sign):
                segments = []
                for i, (met, coeff) in enumerate(metabolites.items()):
                    if i:
                        segments.append((" + ", None))
                    coeff = coeff * sign
                    factor = "" if abs(coeff) == 1.0 else f"{abs(coeff):g} "
                    if factor:
                        segments.append((factor, None))
                    segments.append((met.id, met.id))
                return segments

            reactants = {met: c for met, c in rxn.metabolites.items() if c < 0}
            products = {met: c for met, c in rxn.metabolites.items() if c > 0}
            segments = side_segments(reactants, -1)
            if rxn.reversibility:
                arrow = "<=>"
            elif rxn.upper_bound <= 0:
                arrow = "<--"
            else:
                arrow = "-->"
            segments.append((" " + arrow + " ", None))
            segments.extend(side_segments(products, 1))

            used_px = 0
            for i, (text, met_id) in enumerate(segments):
                used_px += fm.horizontalAdvance(text)
                if used_px > budget_px and i > 0:
                    ellipsis_fmt = QTextCharFormat()
                    ellipsis_fmt.setToolTip(rxn.build_reaction_string())
                    legend_cursor.insertText("…", ellipsis_fmt)
                    return
                if met_id is not None:
                    insert_link(
                        text,
                        "cnapy-metabolite:" + quote(met_id, safe=""),
                        tooltip="Click to select " + met_id,
                    )
                else:
                    legend_cursor.insertText(text)

        for index, (reaction_id, rxn, flux, patch) in enumerate(legend_entries):
            marker_color = to_hex(patch.get_facecolor())

            marker_fmt = QTextCharFormat()
            marker_fmt.setForeground(QColor(marker_color))
            marker_fmt.setFontWeight(QFont.Weight.Bold)
            legend_cursor.insertText("■ ", marker_fmt)

            insert_link(
                reaction_id,
                "cnapy-reaction:" + quote(reaction_id, safe=""),
                bold=False,
            )
            prefix = f": {flux:g}  "
            legend_cursor.insertText(prefix)

            used_px = (
                fm.horizontalAdvance("■ ")
                + fm.horizontalAdvance(reaction_id)
                + fm.horizontalAdvance(prefix)
            )
            insert_reaction_equation(
                rxn, max_equation_lines * cell_inner_width_px - used_px
            )

            if index != len(legend_entries) - 1:
                legend_cursor.insertBlock(line_format)

        legend_cursor.insertBlock(line_format)
        cursor.endEditBlock()

        if not insert_before_prompt:
            # No prompt to preserve in this case -- keep the console's own
            # cursor at the end of what was just appended, as before.
            control.setTextCursor(legend_cursor)
        # When inserting before an existing prompt, Qt automatically keeps
        # every other QTextCursor tied to this document -- including
        # qtconsole's own internal prompt cursor and the widget's visible
        # input caret (and any text already typed there) -- correctly
        # positioned relative to the content just inserted ahead of them,
        # so nothing further needs to be done here.

        # Measure how tall the block we just inserted actually is (from its
        # top down to where the prompt now starts), so the map/console
        # splitter can be grown -- only if it actually needs to be -- to fit
        # the whole thing without scrolling.
        top_cursor = QTextCursor(document)
        top_cursor.setPosition(min(top_of_new_content, document.characterCount() - 1))
        top_rect = control.cursorRect(top_cursor)

        bottom_pos = (
            console_widget._prompt_pos
            if insert_before_prompt
            else document.characterCount() - 1
        )
        bottom_cursor = QTextCursor(document)
        bottom_cursor.setPosition(min(bottom_pos, document.characterCount() - 1))
        bottom_rect = control.cursorRect(bottom_cursor)
        content_height = bottom_rect.bottom() - top_rect.top()

        self._ensure_console_plot_fits(content_height)

        # Re-measure after a possible splitter resize above: that changes
        # the console pane's height (and therefore its scroll range), not
        # its width, so the document's own line-wrapping is unaffected, but
        # the cursor's position relative to the *current* scroll offset can
        # shift slightly.
        top_rect = control.cursorRect(top_cursor)

        # The cell width (and therefore the whole table) is now fixed, so
        # long equations wrap within it instead of forcing a horizontal
        # scroll. Scroll just far enough to bring the *top* of the newly
        # inserted plot into view -- jumping straight to the scrollbar's
        # maximum (as before) shows the bottom of the plot/legend (and the
        # prompt below it) instead, forcing the user to scroll back up to
        # see the top of the image.
        vbar = control.verticalScrollBar()
        margin = 8
        new_scroll_value = vbar.value() + top_rect.top() - margin
        vbar.setValue(max(0, min(new_scroll_value, vbar.maximum())))

        # The figure is no longer needed once its pixels are in the document.
        plt.close(fig)

    def _ensure_console_plot_fits(self, required_height):
        """Grow the console's share of the map/console splitter, if (and
        only if) necessary, so a plot/legend block of ``required_height``
        pixels fits inside the console's visible area without scrolling.

        Space is borrowed from the panes above the console (the map view
        and mode navigator) proportionally to their current size, leaving
        them a reasonable minimum so they never fully collapse.
        """
        splitter = getattr(self.central_widget, "splitter2", None)
        control = self._console_control
        console_widget = self.central_widget.console
        if splitter is None or control is None:
            return

        index = splitter.indexOf(console_widget)
        if index == -1:
            return

        sizes = splitter.sizes()
        if len(sizes) <= index:
            return

        # A small margin so the plot isn't flush against the console's own
        # edges once it fits.
        margin = 16
        needed = required_height + margin
        viewport_height = control.viewport().height()
        if needed <= viewport_height:
            return  # Already fits -- nothing to adjust.

        missing = needed - viewport_height
        other_indices = [i for i in range(len(sizes)) if i != index]
        other_total = sum(sizes[i] for i in other_indices)

        # Keep at least this much combined height for the panes above the
        # console (map view + mode navigator), so they stay usable.
        min_other_total = 300
        available = max(0, other_total - min_other_total)
        grow = min(missing, available)
        if grow <= 0:
            return

        new_sizes = list(sizes)
        for i in other_indices:
            share = sizes[i] / other_total if other_total else 0
            new_sizes[i] = max(0, sizes[i] - round(grow * share))
        new_sizes[index] = sizes[index] + grow
        splitter.setSizes(new_sizes)

    # ------------------------------------------------------------------
    # Hit-testing helpers
    # ------------------------------------------------------------------
    def _find_console_image_at_position(self, pos):
        """Return (image_id, image_rect) for the inline image under *pos*.

        Looking up the image by its document position, rather than relying on
        ``cursorForPosition(pos).charFormat()`` at the mouse position, also
        works in the right-hand part of a wide inline image where Qt can return
        the surrounding table/cell format instead of the image format.
        """
        control = self._console_control
        if control is None:
            return None, None

        document = control.document()
        block = document.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and fragment.charFormat().isImageFormat():
                    image_format = fragment.charFormat().toImageFormat()
                    image_id = image_format.name()
                    if image_id in self._console_plot_regions:
                        cursor = QTextCursor(document)
                        cursor.setPosition(fragment.position())
                        image_rect = control.cursorRect(cursor)
                        width = image_format.width() or self._console_plot_regions[image_id]["image_width"]
                        height = image_format.height() or self._console_plot_regions[image_id]["image_height"]
                        image_rect.setWidth(round(width))
                        image_rect.setHeight(round(height))
                        if image_rect.contains(pos):
                            return image_id, image_rect
                iterator += 1
            block = block.next()

        return None, None

    def _reaction_at_console_plot_position(self, pos):
        """Return the reaction ID under a point in the QtConsole viewport."""
        image_id, image_rect = self._find_console_image_at_position(pos)
        if image_id is None:
            return None

        plot = self._console_plot_regions.get(image_id)
        if plot is None:
            return None

        rel_x = pos.x() - image_rect.left()
        rel_y = pos.y() - image_rect.top()
        if rel_x < 0 or rel_y < 0:
            return None

        displayed_width = image_rect.width()
        displayed_height = image_rect.height()
        if displayed_width <= 0 or displayed_height <= 0:
            return None
        if rel_x >= displayed_width or rel_y >= displayed_height:
            return None

        scale_x = plot["image_width"] / displayed_width
        scale_y = plot["image_height"] / displayed_height
        px = rel_x * scale_x
        py = rel_y * scale_y

        for x0, y0, x1, y1, reaction_id in plot["regions"]:
            if x0 <= px <= x1 and y0 <= py <= y1:
                return reaction_id
        return None

    # ------------------------------------------------------------------
    # Event filter
    # ------------------------------------------------------------------
    def eventFilter(self, watched, event):
        """Handle clickable CNApy links and interactive inline flux plots."""
        console_control = self._console_control
        console_viewport = self._console_viewport
        if console_control is None or watched is not console_viewport:
            return super().eventFilter(watched, event)

        if event.type() == QEvent.Type.MouseMove:
            pos = event.position().toPoint()

            href = console_control.anchorAt(pos)
            if href.startswith(("cnapy-reaction:", "cnapy-metabolite:")):
                # Use the hand cursor only for the explicitly clickable IDs.
                console_viewport.setCursor(Qt.CursorShape.PointingHandCursor)
                QToolTip.hideText()
                self._console_plot_tooltip_reaction = None
                # Swallow the event instead of letting it propagate further.
                # qtconsole's own ConsoleWidget installs an eventFilter on
                # this same viewport (before ours) that unconditionally does
                # QToolTip.showText(pos, anchor) on every MouseMove -- i.e.
                # it immediately shows the raw "cnapy-metabolite:..." href as
                # a tooltip. Because eventFilters run most-recently-installed
                # first, returning True here stops that call from firing, so
                # only Qt's own per-character tooltip (the friendly "Click to
                # select ..." text set via QTextCharFormat.setToolTip(),
                # shown through the unrelated QEvent.ToolTip mechanism) is
                # ever displayed, instead of the raw href flashing first.
                return True

            reaction_id = self._reaction_at_console_plot_position(pos)
            if reaction_id is not None:
                # Keep the standard arrow cursor over the plot.
                console_viewport.setCursor(Qt.CursorShape.ArrowCursor)
                # Stop propagation so the console cannot dismiss/reposition
                # the tooltip on every move.
                if reaction_id != self._console_plot_tooltip_reaction:
                    QToolTip.showText(
                        event.globalPosition().toPoint(),
                        reaction_id,
                        console_viewport,
                        QRect(),
                        10000,
                    )
                    self._console_plot_tooltip_reaction = reaction_id
                return True

            if self._console_plot_tooltip_reaction is not None:
                QToolTip.hideText()
                self._console_plot_tooltip_reaction = None
            console_viewport.setCursor(Qt.CursorShape.ArrowCursor)
            return False

        if (
            event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
        ):
            pos = event.position().toPoint()
            href = console_control.anchorAt(pos)

            if href.startswith("cnapy-reaction:"):
                self.reactionClicked.emit(
                    unquote(href[len("cnapy-reaction:"):])
                )
                return True

            if href.startswith("cnapy-metabolite:"):
                self.metaboliteClicked.emit(
                    unquote(href[len("cnapy-metabolite:"):])
                )
                return True

            reaction_id = self._reaction_at_console_plot_position(pos)
            if reaction_id is not None:
                self.reactionClicked.emit(reaction_id)
                return True

        return super().eventFilter(watched, event)
