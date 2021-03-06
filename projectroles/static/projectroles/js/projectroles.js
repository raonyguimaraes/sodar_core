/*
 General SODAR Core / projectroles javascript
 */


/* Cross Site Request Forgery protection for Ajax views --------------------- */


// From: https://stackoverflow.com/a/47878344
var csrfToken = jQuery("[name=csrfmiddlewaretoken]").val();

function csrfSafeMethod(method) {
    // these HTTP methods do not require CSRF protection
    return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
}

// set CSRF header
$.ajaxSetup({
    beforeSend: function (xhr, settings) {
        if (!csrfSafeMethod(settings.type) && !this.crossDomain) {
            xhr.setRequestHeader("X-CSRFToken", csrfToken);
        }
    }
});


/* Print out human readable file size --------------------------------------- */


// From: https://stackoverflow.com/a/14919494
function humanFileSize(bytes, si) {
    var thresh = si ? 1000 : 1024;
    if (Math.abs(bytes) < thresh) {
        return bytes + ' B';
    }
    var units = si
        ? ['kB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
        : ['KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB'];
    var u = -1;
    do {
        bytes /= thresh;
        ++u;
    } while (Math.abs(bytes) >= thresh && u < units.length - 1);
    return bytes.toFixed(1) + ' ' + units[u];
}


/* Bootstrap popover and tooltip setup -------------------------------------- */


// Bootstrap popover
$('[data-toggle="popover"]').popover({
    container: 'body',
    sanitize: false
});

// Bootstrap tooltip
$(function () {
    // For cases where data-toggle is also needed for another functionality
    $('[data-tooltip="tooltip"]').tooltip({
        trigger: 'hover'
    });
    $('[data-toggle="tooltip"]').tooltip({
        trigger: 'hover'
    });
});


/* Shepherd tour ------------------------------------------------------------ */


var tourEnabled = false;  // Needs to set true if there is content
tour = new Shepherd.Tour({
    defaults: {
        classes: 'shepherd-theme-default'
    }
});

// Set up tour link
$(document).ready(function () {
    if (tourEnabled === false) {
        $('#site-help-link').addClass('disabled').removeClass('text-warning');
    }

    $('#site-help-link').click(function () {
        tour.start();
    });
});


/* Search form setup -------------------------------------------------------- */


// Disable nav project search until 3+ characters have been input
// (not counting keyword)
function modifySearch() {
    var v = $('#sodar-nav-search-input').val();

    if (v.length > 2) {
        $('#sodar-nav-search-submit').attr('disabled', false);
    } else {
        $('#sodar-nav-search-submit').attr('disabled', true);
    }
}

$(document).ready(function () {
    if ($('#sodar-nav-search-input').val().length === 0) {
      $('#sodar-nav-search-submit').attr('disabled', true);
    } else {
      $('#sodar-nav-search-submit').attr('disabled', false);
    }
    $('#sodar-nav-search-input').keyup(function () {
        modifySearch();
    }).on('input', function () {
        modifySearch();
    });
});


/* Table cell overflow handling --------------------------------------------- */


function modifyCellOverflow() {
    $('.sodar-overflow-container').each(function () {
        var parentWidth = $(this).parent().width();
        var lastVisibleTd = false;

        // Don't allow adding hover to last visible td for now
        if ($(this).parent().is($(this).closest('td')) &&
            $(this).closest('td').is($(this).closest('tr').find('td:visible:last'))) {
            lastVisibleTd = true;
        }

        if ($(this).hasClass('sodar-overflow-hover') && (
            lastVisibleTd === true || $(this).prop('scrollWidth') <= parentWidth)) {
            $(this).removeClass('sodar-overflow-hover');
        } else if ($(this).prop('scrollWidth') > parentWidth &&
            !$(this).hasClass('sodar-overflow-hover') &&
            !$(this).hasClass('sodar-overflow-hover-disable') &&
            lastVisibleTd === false) {
            $(this).addClass('sodar-overflow-hover');
        }
    });
}

// On document load, enable/disable all overflow containers
$(document).ready(function () {
    modifyCellOverflow();
});

// On window resize, enable/disable all overflow containers
$(window).resize(function () {
    if (typeof (window.refreshCellOverflow) === 'undefined' ||
        window.refreshCellOverflow !== false) {
        modifyCellOverflow();
    }
});


/* Project list filtering --------------------------------------------------- */


// TODO: Refactor or implement with DataTables
$(document).ready(function () {
    $('.sodar-pr-home-display-filtered').hide();
    $('.sodar-pr-home-display-notfound').hide();
    $('.sodar-pr-home-display-nostars').hide();

    // Filter input
    $('#sodar-pr-project-list-filter').keyup(function () {
        var v = $(this).val().toLowerCase();
        var valFound = false;
        $('.sodar-pr-home-display-nostars').hide();

        if (v.length > 2) {
            $('.sodar-pr-home-display-default').hide();
            $('#sodar-pr-project-list-filter').removeClass('text-danger').addClass('text-success');
            $('#sodar-pr-project-list-link-star').html('<i class="fa fa-star-o"></i> Starred');

            $('.sodar-pr-home-display-filtered').each(function () {
                var titleTxt = $(this).find('td:first-child').attr('orig-txt');
                var titleLink = $(this).find('td:first-child div a');

                if (titleLink.text().toLowerCase().indexOf(v) !== -1 ||
                    titleLink.attr('data-original-title').toLowerCase().indexOf(v) !== -1) {
                    // Reset content for updating the highlight
                    titleLink.html(titleTxt);

                    // Highlight
                    var pattern = new RegExp("(" + v + ")", "gi");
                    var titlePos = titleTxt.toLowerCase().indexOf(v);

                    if (titlePos !== -1) {
                        var titleVal = titleTxt.substring(titlePos, titlePos + v.length);
                        titleLink.html(titleTxt.replace(pattern, '<span class="sodar-search-highlight">' + titleVal + '</span>'));
                    }

                    $(this).show();
                    valFound = true;
                    $('.sodar-pr-home-display-notfound').hide();
                } else {
                    $(this).hide();
                }
            });

            if (valFound === false) {
                $('.sodar-pr-home-display-notfound').show();
            }
        } else {
            $('.sodar-pr-home-display-default').show();
            $('.sodar-pr-home-display-filtered').hide();
            $('.sodar-pr-home-display-notfound').hide();
            $('#sodar-pr-project-list-filter').addClass(
                'text-danger').removeClass('text-success');
            $('#sodar-pr-project-list-link-star').attr('filter-mode', '0');
        }

        // Update overflow status
        modifyCellOverflow();
    });

    // Filter by starred
    $('#sodar-pr-project-list-link-star').click(function () {
        $('.sodar-pr-home-display-notfound').hide();

        // Reset search terms
        $('.sodar-pr-home-display-filtered').each(function () {
            // Reset filter highlights and value
            var titleTxt = $(this).find('td:first-child').attr('orig-txt');
            $(this).find('td:first-child a').html(titleTxt);
            $(this).hide();
            $('#sodar-pr-project-list-filter').val('');
        });

        if ($(this).attr('filter-mode') === '0') {
            $('.sodar-pr-home-display-default').hide();
            $('.sodar-pr-home-display-starred').show();
            $('#sodar-pr-project-list-link-star').html(
                '<i class="fa fa-star"></i> Starred');
            $(this).attr('filter-mode', '1');

            if ($('.sodar-pr-home-display-starred').length === 0) {
                $('.sodar-pr-home-display-nostars').show();
            }
        } else if ($(this).attr('filter-mode') === '1') {
            $('.sodar-pr-home-display-nostars').hide();
            $('.sodar-pr-home-display-default').show();
            $('#sodar-pr-project-list-link-star').html(
                '<i class="fa fa-star-o"></i> Starred');
            $(this).attr('filter-mode', '0');
        }

        // Update overflow status
        modifyCellOverflow();
    });
});


/* Star/unstar project ------------------------------------------------------ */


$(document).ready(function () {
    $('#sodar-pr-link-project-star').click(function () {
        $.post({
            url: $(this).attr('star-url'),
            method: 'POST',
            dataType: 'json'
        }).done(function (data) {
            console.log('Star clicked: ' + data);  // DEBUG
            if (data === 1) {
                $('#sodar-pr-btn-star-icon').removeClass(
                    'text-muted').addClass('text-warning').removeClass(
                    'fa-star-o').addClass('fa-star');
                $('#sodar-pr-link-project-star').attr(
                    'data-original-title', 'Unstar');
            } else {
                $('#sodar-pr-btn-star-icon').removeClass(
                    'text-warning').addClass('text-muted').removeClass(
                    'fa-star').addClass('fa-star-o');
                $('#sodar-pr-link-project-star').attr(
                    'data-original-title', 'Star');
            }
        }).fail(function () {
            alert('Error: unable to set project star!');
        });
    });
});


/* Improve the responsiveness of the title bar ------------------------------ */


$(window).on('resize', function () {
    if ($(this).width() < 750) {
        $('#sodar-base-navbar-nav').removeClass('ml-auto').addClass('mr-auto');
    } else {
        $('#sodar-base-navbar-nav').removeClass('mr-auto').addClass('ml-auto');
    }
});


/* Toggle sticky subtitle container shadow when scrolling ------------------- */


$(document).ready(function () {
    $('.sodar-app-container').scroll(function () {
        var container = $('.sodar-subtitle-container');
        var scroll = $('.sodar-app-container').scrollTop();

        if (container != null && container.hasClass('sticky-top')) {
            if (scroll >= 80) {
                container.addClass('sodar-subtitle-shadow');
            } else {
                container.removeClass('sodar-subtitle-shadow');
            }
        }
    });
});


/* Initialize Clipboard.js for common buttons ------------------------------- */

$(document).ready(function() {
    /***************
     Init Clipboards
     ***************/
    new ClipboardJS('.sodar-copy-btn');

    /******************
     Copy link handling
     ******************/
    $('.sodar-copy-btn').click(function () {
        // NOTE: Temporary hack, see issue #333
        var icon = $(this).find('i');
        var mutedRemoved = false;

        // Title bar links are currently rendered a bit differently
        if (icon.hasClass('text-muted')) {
            icon.removeClass('text-muted');
            mutedRemoved = true;
        }

        icon.addClass('text-warning');

        var realTitle = $(this).tooltip().attr('data-original-title');
        $(this).attr('title', 'Copied!')
            .tooltip('_fixTitle')
            .tooltip('show')
            .attr('title', realTitle)
            .tooltip('_fixTitle');

        $(this).delay(250).queue(function() {
            icon.removeClass('text-warning');

            if (mutedRemoved) {
                icon.addClass('text-muted');
            }

            $(this).dequeue();
        });
    });
});


/* Display unsupported browser warning -------------------------------------- */


$(document).ready(function () {
    if (window.sodarBrowserWarning === 1) {
        // Based on https://stackoverflow.com/a/38080051
        navigator.browserSpecs = (function(){
            var ua = navigator.userAgent, tem,
                M = ua.match(/(opera|chrome|safari|firefox|msie|trident(?=\/))\/?\s*(\d+)/i) || [];
            if(/trident/i.test(M[1])) {
                tem = /\brv[ :]+(\d+)/g.exec(ua) || [];
                return {name: 'IE', version: (tem[1] || '')};
            }
            if(M[1] === 'Chrome'){
                tem = ua.match(/\b(OPR|Edge)\/(\d+)/);
                if (tem != null) return {name: tem[1].replace(
                    'OPR', 'Opera'), version: tem[2]};
            }
            M = M[2] ? [M[1], M[2]]: [navigator.appName, navigator.appVersion, '-?'];
            if ((tem = ua.match(/version\/(\d+)/i)) != null)
                M.splice(1, 1, tem[1]);
            return {name: M[0], version: M[1]};
        })();

        if (!['Chrome', 'Firefox', 'Edge'].includes(navigator.browserSpecs.name)) {
            let parentElem = $('div.sodar-app-container');

            if (!parentElem.length) {
                parentElem = $('div.sodar-content-container').find(
                    'div.container-fluid').first();
            }

            if (!$('div.sodar-alert-container').length) {
                parentElem.prepend(
                    '<div class="container-fluid sodar-alert-container"></div>');
            }

            $('div.sodar-alert-container').prepend(
                '<div class="alert alert-danger sodar-alert-top">' +
                '<i class="fa fa-exclamation-triangle"></i> ' +
                'You are using an unsupported browser. We recommend using ' +
                'a recent version of ' +
                '<a href="https://www.mozilla.org/firefox/new" target="_blank">Mozilla Firefox</a> or ' +
                '<a href="https://www.google.com/chrome" target="_blank">Google Chrome</a>.' +
                '</div>');
        }
    }
});


/* Hide sidebar based on element count -------------------------------------- */


function toggleSidebar() {
    if (!window.sidebar.is(':visible')) {
        if (window.sidebarMinWindowHeight < window.innerHeight && window.innerWidth > 1000) {
            window.sidebar.show();
            window.sidebar_alt_btn.hide();
        }
    } else if (window.sidebarMinWindowHeight > window.innerHeight || window.innerWidth < 1000) {
        window.sidebar_alt_btn.show();
        window.sidebar.hide();
    }
}

$(document).ready(function () {
    // Remember sidebar total height
    window.sidebar = $('#sodar-pr-sidebar');
    window.sidebar_alt_btn = $('#sodar-pr-sidebar-alt-btn');
    let sidebarContent = $('#sodar-pr-sidebar-navbar').get(0);
    if (sidebarContent)
        window.sidebarMinWindowHeight = sidebarContent.scrollHeight + sidebarContent.getBoundingClientRect().top;
    toggleSidebar();

});

$(window).on('resize', function () {
    toggleSidebar();
});
