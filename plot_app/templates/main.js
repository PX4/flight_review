
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

function init_error_labels(error_ids) {
    // initialize error labels

    $("#error-label > option").each(function(){
        if(error_ids.includes(parseInt($(this).attr('data-id')))){
            if(!$(this).prop('selected')){
                $(this).prop('selected', true)
            }
        } else{
            if($(this).prop('selected')){
                $(this).prop('selected', false)
            }
        }
    });

    $("#error-label").trigger('chosen:updated')
}

$(function() { //on startup

	// Show Logging start: convert timestamp to local time
	var logging_span = $('#logging-start-element');

	var d = new Date(0);
	d.setUTCSeconds(logging_span.text());
	var date_str = ("0" + d.getDate()).slice(-2) + "-" +
		("0"+(d.getMonth()+1)).slice(-2) + "-" + d.getFullYear() + " " +
		("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2);
	logging_span.text(date_str);
	logging_span.show();


	// init error labels
    var error_labels = $("#error-label");
	error_labels.chosen({
        no_results_text: "Oops, nothing found!",
        width: "100%"
    });

    error_labels.change(function () {

		var error_ids = [];
        $("#error-label > option").each(function() {
            if($(this).prop('selected')) {
				var id = parseInt($(this).attr('data-id'));
				error_ids.push(id);
            }
        });

        $.ajax({
            type: "POST",
            url: "/error_label",
            data: JSON.stringify({ 'log' : "{{log_id}}", 'labels' : error_ids }),
            dataType: "json"
        });
    });

    init_error_labels({{cur_err_ids}});
});

function setupPlots() {
	// do necessary setup after plots are loaded

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


	// add fragment anchor links to each plot (placement via CSS)
	function foreach_plot_view(view, fn) {
		if (view.model instanceof Bokeh.Models("Plot")) {
			fn(view);
		} else if (view.model instanceof Bokeh.Models("LayoutDOM")) {
			for (var id in view.child_views) {
				foreach_plot_view(view.child_views[id], fn);
			}
		}
	}
	var root = Bokeh.index[Object.keys(Bokeh.index)[0]];
	foreach_plot_view(root, function(plot_view) {
		index_of = plot_ids.indexOf(plot_view.model.id)
		if (index_of >= 0) {
			var a = $('<a id="'+plot_fragments[index_of]+'" '+
					'class="fragment bk-plot-layout"' +
					' href="#'+plot_fragments[index_of]+'"><big>&para;</big></a>');
			$(plot_view.canvas_view.el).before(a);
		}
	});


	$('#loading-plots').hide();

	$('#show-additional-data-btn').click(function(){
		$(this).text(function(i,old){
			return old.includes('Show') ?  'Hide additional Data' : 'Show additional Data';
		});
	});

	// because bokeh dynamically loads the content after startup, jumping to
	// fragments does not work on page load, so we do it manually
	var cur_frag = window.location.hash.substr(1);
	if (cur_frag.length > 0) {
		window.setTimeout(function() { $('#'+cur_frag).scrollView(); }, 1000);
	}
}

function renderingCompleteCheck() {

    function done() {
		console.log('rendering done');
		setupPlots();
    }

	// wait until the document exists
	if (window.Bokeh.documents.length == 0) {
		window.setTimeout(renderingCompleteCheck, 100);
		return;
	}

    var doc = window.Bokeh.documents[0];

    if (doc.is_idle) {
		done();
	} else {
		doc.idle.connect(done);
	}
}

$(function() { //on startup
	window.setTimeout(renderingCompleteCheck, 1);
});

$(document).ready(function(){
	// initialize the tooltip's
	$('[data-toggle="tooltip"]').tooltip({html: true});
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

	/* google maps resize */
	if (typeof(g_google_map) !== "undefined" && g_google_map != null) {
		google.maps.event.trigger(g_google_map, "resize");
	}

	// FIXME: this is supposed to work, but it does not (with bokeh 0.12.14) :/
	for (var key in Bokeh.index) {
		Bokeh.index[key].resize();
	}
}

{% endif %} {# is_plot_page #}


{% if is_stats_page %}
// ok, this is ugly: there are too many hover tools (one per airframe in a
// single plot), so hide them from the toolbar here. Some actions like resetting
// the plot make them reappear, so we continuously repeat the call.
function hide_bokeh_hover_tool() {
	$(".bk-tool-icon-hover").parent('div').css("display", "none");
	window.setTimeout(hide_bokeh_hover_tool, 200);
}

$(function() { //on startup
	window.setTimeout(hide_bokeh_hover_tool, 500);
});

{% endif %} {# is_stats_page #}

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
