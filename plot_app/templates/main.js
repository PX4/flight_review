
$.fn.scrollView = function () {
    return this.each(function () {
        $('html, body').animate({
            scrollTop: $(this).offset().top
        }, 500);
    });
}

var do_not_scroll = false;
function navigate(fragment) {
	// jump to the fragment and handle the sticky header properly
	do_not_scroll = true;
	window.location.hash = fragment;

	setTimeout(function() {
		//hide sticky header
		var elSelector		= '#header',
		$element		= $( elSelector );
		elHeight		= $element.outerHeight();
		$element.css( 'top', -elHeight );
		do_not_scroll = false;
	}, 10);
}

{% if is_plot_page %}

function checkPlotsInitialized() {
	// check if plots are fully initialized and do the necessary setup.
	// we cannot rely on a specific event for this as bokeh dynamically loads
	// the plots after startup

	var plot_ids = [
{% set comma = joiner(",") %}
{% for cur_plot in plots %}
	{{ comma() }} "{{ cur_plot.model_id }}"
{% endfor %}
	];

	var plot_fragments = [
{% set comma = joiner(",") %}
{% for cur_plot in plots %}
	{{ comma() }} "{{ cur_plot.fragment }}"
{% endfor %}
	];

	for (var i = 0; i < plot_ids.length; ++i) {
		if (!$('#modelid_'+plot_ids[i]).length) {
			window.setTimeout(checkPlotsInitialized, 500);
			return; // not yet loaded
		}
	}


	// if we get here, all plots are loaded

	// add fragment anchor links to each plot (placement via CSS)
	for (var i = 0; i < plot_ids.length; ++i) {
		$('#modelid_'+plot_ids[i]).before('<a id="'+plot_fragments[i]+'" '+
			'class="fragment bk-plot-layout"' +
			' href="#'+plot_fragments[i]+'"><big>&para;</big></a>');
	}

	$('#loading-plots').hide();

	// because bokeh dynamically loads the content after startup, jumping to
	// fragments does not work on page load, so we do it manually
	var cur_frag = window.location.hash.substr(1);
	if (cur_frag.length > 0) {
		window.setTimeout(function() { $('#'+cur_frag).scrollView(); }, 1000);
	}
}

$(function() { //on startup
	window.setTimeout(checkPlotsInitialized, 500);
});

/* resize the plots */
function setSize(size) {
	console.log(size);

	var sizes = { small: 0.8, medium: 1, large: 1.4, xlarge: 2.1 };
	for(key in sizes) {
		$('#size-'+key+'-menu').removeClass('active');
	}
	$('#size-'+size+'-menu').addClass('active');

	var slider_value = sizes[size];

	$(document.body).css('max-width', Math.floor(900*slider_value)+'px')

	if (slider_value < 1) slider_value = 1;
	if (slider_value > 2) slider_value = 2;
	$(document.body).css('width', Math.floor(75+(slider_value-1)*15)+'%')

	/* get the bokeh document. If we had a bokeh object, like a plot, we
	could use plot.document. The following works w/o, but maybe there's a
	simpler way? */
	bokeh_doc = Bokeh.index[Object.keys(Bokeh.index)[0]].model.document
	bokeh_doc.resize(); //trigger resize event

	/* google maps resize */
	if (typeof(g_google_map) !== "undefined" && g_google_map != null) {
		google.maps.event.trigger(g_google_map, "resize");
	}
}

{% endif %} {# is_plot_page #}


// auto-hide sticky header when scrolling down, show when scrolling up
// source: http://osvaldas.info/auto-hide-sticky-header
;( function( $, window, document, undefined )
		{
			'use strict';

			var elSelector		= '#header',
			$element		= $( elSelector );

			if( !$element.length ) return true;

			var elHeight		= 0,
			elTop			= 0,
			$document		= $( document ),
			dHeight			= 0,
			$window			= $( window ),
			wHeight			= 0,
			wScrollCurrent	= 0,
			wScrollBefore	= 0,
			wScrollDiff		= 0;

			$window.on( 'scroll', function()
					{
						elHeight		= $element.outerHeight();
						dHeight			= $document.height();
						wHeight			= $window.height();
						wScrollCurrent	= $window.scrollTop();
						wScrollDiff		= wScrollBefore - wScrollCurrent;
						elTop			= parseInt( $element.css( 'top' ) ) + wScrollDiff;

						if (do_not_scroll) {
							wScrollBefore = wScrollCurrent;
							return;
						}

						if( wScrollCurrent <= 0 ) // scrolled to the very top; element sticks to the top
							$element.css( 'top', 0 );

						else if( wScrollDiff > 0 ) // scrolled up; element slides in
							$element.css( 'top', elTop > 0 ? 0 : elTop );

						else if( wScrollDiff < 0 ) // scrolled down
						{
							// scrolled down; element slides out
							$element.css( 'top', Math.abs( elTop ) > elHeight ? -elHeight : elTop );
						}

						wScrollBefore = wScrollCurrent;
					});

		})( jQuery, window, document );
